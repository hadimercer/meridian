"""
pipeline/db.py
Supabase connection helpers for Meridian.
All database access goes through this module.

WARNING — get_supabase_admin() returns a service-role client that bypasses
Row Level Security.  It must NEVER be passed to or called from frontend code.
"""

import os

import pandas as pd
import psycopg2
import streamlit as st
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


# ─── Private helpers ─────────────────────────────────────────────────────────

def _get_secret(key: str) -> str:
    """
    Resolve a secret by name.

    Tries st.secrets first (Streamlit Cloud), then falls back to os.environ
    (local development via .env loaded above).  Returns None if the key is
    absent in both sources.
    """
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key)


# ─── Supabase client (used for Auth and realtime) ────────────────────────────

def get_supabase_client() -> Client:
    """
    Return a Supabase client authenticated with the anon key.

    Intentionally not cached — Auth state is per-session and must not bleed
    between Streamlit reruns or users.
    """
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_ANON_KEY")
    return create_client(url, key)


# WARNING: the client returned below bypasses Row Level Security.
# Never pass it to frontend code or expose it in any user-facing path.

def get_supabase_admin() -> Client:
    """
    Return a Supabase client authenticated with the service-role key.

    Used ONLY by the scoring engine to write to rag_scores, where RLS must be
    bypassed.  This client must never be passed to or called from frontend code.
    """
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


# ─── Direct psycopg2 connection (used by scoring engine) ─────────────────────

def get_pg_connection():
    """
    Return a raw psycopg2 connection to Supabase PostgreSQL.

    sslmode is set to 'require' and connect_timeout to 15 seconds.
    The caller is responsible for closing the connection when finished.
    """
    return psycopg2.connect(
        host=_get_secret("DB_HOST"),
        port=_get_secret("DB_PORT"),
        dbname=_get_secret("DB_NAME"),
        user=_get_secret("DB_USER"),
        password=_get_secret("DB_PASSWORD"),
        sslmode="require",
        connect_timeout=15,
    )


# ─── Cached query helper ─────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """
    Execute a parameterised SELECT query and return results as a DataFrame.

    Opens and closes its own psycopg2 connection.  Results are cached for 60
    seconds to reduce round-trips on repeated Streamlit reruns.  Returns an
    empty DataFrame (never None) when the query produces no rows.  Use for
    READ operations only — do not use for scoring writes.
    """
    conn = get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows)
    finally:
        conn.close()


# ─── Write query helper ───────────────────────────────────────────────────────

def run_query(sql: str, params: tuple = ()) -> None:
    """
    Execute a parameterised write query (INSERT, UPDATE, or DELETE) and commit.

    Opens and closes its own psycopg2 connection.  Not cached.  Raises any
    database exception to the caller — exceptions are never swallowed silently.
    Returns None on success.
    """
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
