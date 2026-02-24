"""
pipeline/db.py
Supabase connection helpers for Meridian.
All database access goes through this module.
"""

import os
import psycopg2
import streamlit as st
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


# ─── Supabase client (used for Auth and realtime) ────────────────────────────

def get_supabase_client() -> Client:
    """Return an authenticated Supabase client using the anon key."""
    url  = os.environ["SUPABASE_URL"]
    key  = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def get_supabase_admin() -> Client:
    """
    Return a Supabase client using the service role key.
    Used by the scoring engine to write to rag_scores (bypasses RLS).
    NEVER expose this client or its key in the frontend.
    """
    url  = os.environ["SUPABASE_URL"]
    key  = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


# ─── Direct psycopg2 connection (used by scoring engine) ─────────────────────

def get_pg_connection():
    """
    Return a raw psycopg2 connection to Supabase PostgreSQL.
    Used for complex scoring queries that benefit from direct SQL.
    Caller is responsible for closing the connection.
    """
    return psycopg2.connect(
        host     = os.environ["DB_HOST"],
        port     = os.environ["DB_PORT"],
        dbname   = os.environ["DB_NAME"],
        user     = os.environ["DB_USER"],
        password = os.environ["DB_PASSWORD"],
        sslmode  = "require",
        connect_timeout = 15,
    )


# ─── Cached query helper ─────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def query_df(sql: str, params: tuple = ()):
    """
    Execute a SQL query and return results as a list of dicts.
    Cached for 60 seconds to reduce round-trips on repeated renders.
    Use for READ operations only. Do not use for scoring writes.
    """
    import pandas as pd
    conn = get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall())
    finally:
        conn.close()
