"""
pipeline/auth.py
Session management and role helpers for Meridian.
Wraps Supabase Auth so the rest of the app never calls it directly.
"""

import streamlit as st
from pipeline.db import get_supabase_client, query_df

# Role precedence — higher number = more privileged.
_ROLE_RANK = {"viewer": 0, "contributor": 1, "owner": 2}


# ─── Session accessors ────────────────────────────────────────────────────────

def get_current_user() -> dict | None:
    """
    Return the current authenticated user dict from session state.

    The dict contains at minimum 'id' (UUID string) and 'email'.
    Returns None if no active session exists.
    """
    return st.session_state.get("user", None)


def get_current_user_id() -> str | None:
    """
    Return the current user's UUID string, or None if not authenticated.

    Convenience wrapper around get_current_user() so callers never have to
    guard against a missing 'id' key themselves.
    """
    user = get_current_user()
    return getattr(user, "id", None) if user is not None else None


def is_authenticated() -> bool:
    """Return True if a user session is currently active."""
    return get_current_user() is not None


# ─── Auth guards ──────────────────────────────────────────────────────────────

def require_auth() -> None:
    """
    Guard for pages that require authentication.

    Call at the top of any Streamlit page that must not be visible to
    unauthenticated visitors.  Redirects to the login page immediately if no
    session is active — Streamlit stops rendering the rest of the page.
    """
    if not is_authenticated():
        st.switch_page("pages/login.py")


def require_role(workstream_id: str, minimum_role: str) -> None:
    """
    Enforce a minimum role for a workstream action.

    minimum_role must be 'contributor' or 'owner'.  If the current user's role
    rank is below the required rank (or they have no role at all), displays an
    error message and calls st.stop() so the rest of the page does not execute.
    """
    role = get_user_role(workstream_id, get_current_user_id())
    user_rank    = _ROLE_RANK.get(role, -1)
    required_rank = _ROLE_RANK.get(minimum_role, 99)
    if user_rank < required_rank:
        st.error("You don't have permission to do that.")
        st.stop()


# ─── Role queries ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def get_user_role(workstream_id: str, user_id: str) -> str | None:
    """
    Return the user's role in a workstream, or None if they are not a member.

    Possible return values: 'owner' | 'contributor' | 'viewer' | None.
    None means the user has no active membership (not a member, or a former
    member with is_former_member = TRUE).

    Accepts user_id as an explicit parameter (not read from session state
    inside the function) so that st.cache_data can key correctly on it.
    Call as: get_user_role(workstream_id, get_current_user_id())

    Cached for 30 seconds — role changes are infrequent but should propagate
    within half a minute without requiring a manual cache clear.
    """
    if user_id is None:
        return None

    sql = """
        SELECT role
        FROM workstream_members
        WHERE workstream_id      = %s
          AND user_id            = %s
          AND is_former_member   = FALSE
    """
    df = query_df(sql, (workstream_id, user_id))
    if df.empty:
        return None
    return df.iloc[0]["role"]


def is_owner(workstream_id: str) -> bool:
    """
    Return True if the current user is an owner of the given workstream.
    """
    return get_user_role(workstream_id, get_current_user_id()) == "owner"


def is_contributor_or_above(workstream_id: str) -> bool:
    """
    Return True if the current user is a contributor or owner of the workstream.

    Returns False for viewers, non-members, and unauthenticated users.
    """
    role = get_user_role(workstream_id, get_current_user_id())
    return role in ("owner", "contributor")


# ─── Workstream listing ───────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def get_user_workstreams(user_id: str):
    """
    Return a DataFrame of all active workstreams the user is a member of.

    Columns include all workstreams fields plus 'role' and 'joined_at' from
    the membership table.  Archived workstreams and former memberships are
    excluded.  Results are ordered by workstream updated_at descending so
    the most recently active workstream appears first.

    Accepts user_id as an explicit parameter so st.cache_data can key on it.
    Returns an empty DataFrame if the user has no active memberships.
    """
    sql = """
        SELECT w.*, wm.role, wm.joined_at
        FROM   workstreams       w
        JOIN   workstream_members wm ON wm.workstream_id = w.id
        WHERE  wm.user_id          = %s
          AND  wm.is_former_member = FALSE
          AND  w.is_archived       = FALSE
        ORDER BY w.updated_at DESC
    """
    return query_df(sql, (user_id,))


# ─── Session teardown ─────────────────────────────────────────────────────────

def logout() -> None:
    """
    Sign the current user out and redirect to the login page.

    Clears 'user' and 'session' from st.session_state, calls Supabase Auth
    sign_out to invalidate the server-side session token, then redirects.
    Any error from sign_out is ignored — the local session is always cleared.
    """
    st.session_state.pop("user", None)
    st.session_state.pop("session", None)
    try:
        get_supabase_client().auth.sign_out()
    except Exception:
        pass
    st.switch_page("pages/login.py")
