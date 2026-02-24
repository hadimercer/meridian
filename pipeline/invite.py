"""
pipeline/invite.py
Invite link generation and token resolution for Meridian.
"""

import streamlit as st
from pipeline.db import get_pg_connection, query_df, run_query


def _build_invite_url(token: str) -> str:
    """Return a full login URL for an invite token."""
    base = st.secrets.get("APP_URL", "http://localhost:8501")
    return f"{base}/pages/login.py?invite={token}"


def _get_pg_connection():
    """Return a psycopg2 connection via the shared DB helper internals."""
    get_pg_connection = run_query.__globals__.get("get_pg_connection")
    if get_pg_connection is None:
        raise RuntimeError("Database connection helper is unavailable.")
    return get_pg_connection()


def generate_invite_link(workstream_id: str, created_by: str) -> str:
    """
    Deactivate existing active links and create a new invite link URL.

    Existing active links for the workstream are first marked inactive.
    A new row is then inserted and its generated token is returned as a full
    login URL.
    """
    run_query(
        """
        UPDATE invite_links
        SET is_active = FALSE
        WHERE workstream_id = %s AND is_active = TRUE
        """,
        (workstream_id,),
    )

    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO invite_links (workstream_id, created_by)
                VALUES (%s, %s)
                RETURNING token
                """,
                (workstream_id, created_by),
            )
            token = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return _build_invite_url(token)


def resolve_invite_token(token: str) -> dict | None:
    """
    Look up an active invite token.

    Returns the invite_links row dict, or None if token is invalid/inactive.
    """
    df = query_df(
        """
        SELECT *
        FROM invite_links
        WHERE token = %s AND is_active = TRUE
        """,
        (token,),
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def accept_invite(token: str, user_id: str) -> bool:
    """
    Add a user to the workstream as Viewer after they register/log in via invite link.

    Returns True when the invite is accepted idempotently, and False for an
    invalid token or any processing error.
    """
    try:
        invite = resolve_invite_token(token)
        if invite is None:
            return False

        workstream_id = invite["workstream_id"]
        membership_df = query_df(
            """
            SELECT id, is_former_member
            FROM workstream_members
            WHERE workstream_id = %s AND user_id = %s
            """,
            (workstream_id, user_id),
        )

        if membership_df.empty:
            run_query(
                """
                INSERT INTO workstream_members (workstream_id, user_id, role)
                VALUES (%s, %s, 'viewer')
                """,
                (workstream_id, user_id),
            )
            return True

        membership = membership_df.iloc[0].to_dict()
        if membership.get("is_former_member"):
            run_query(
                """
                UPDATE workstream_members
                SET is_former_member = FALSE, role = 'viewer'
                WHERE id = %s
                """,
                (membership["id"],),
            )
        return True
    except Exception:
        return False


def get_active_invite_url(workstream_id: str) -> str | None:
    """
    Return the full URL for an active invite link on a workstream.

    Returns None when no active invite exists.
    """
    df = query_df(
        """
        SELECT token
        FROM invite_links
        WHERE workstream_id = %s AND is_active = TRUE
        LIMIT 1
        """,
        (workstream_id,),
    )
    if df.empty:
        return None

    token = df.iloc[0]["token"]
    return _build_invite_url(token)
