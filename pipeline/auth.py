"""
pipeline/auth.py
Session management and role helpers for Meridian.
Wraps Supabase Auth so the rest of the app never calls it directly.
"""

import streamlit as st
from pipeline.db import get_supabase_client


def get_current_user():
    """
    Return the current authenticated user dict from session state,
    or None if no active session.
    """
    return st.session_state.get("user", None)


def is_authenticated() -> bool:
    """Return True if a user session is active."""
    return get_current_user() is not None


def get_user_role(workstream_id: str) -> str | None:
    """
    Return the current user's role in a given workstream.
    Returns 'owner' | 'contributor' | 'viewer' | None.
    None means the user is not a member (or is a former member).
    """
    # TODO: implement — query workstream_members via Supabase client
    raise NotImplementedError


def require_auth():
    """
    Call at the top of any page that requires authentication.
    Redirects to login if no active session.
    """
    if not is_authenticated():
        st.switch_page("pages/login.py")


def require_role(workstream_id: str, minimum_role: str):
    """
    Enforce a minimum role for an action.
    minimum_role: 'contributor' or 'owner'
    Displays an error and stops execution if the user's role is insufficient.
    """
    role = get_user_role(workstream_id)
    role_rank = {"viewer": 0, "contributor": 1, "owner": 2}
    if role is None or role_rank.get(role, -1) < role_rank.get(minimum_role, 99):
        st.error("You do not have permission to perform this action.")
        st.stop()
