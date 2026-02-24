"""
pages/login.py
Login and registration page.
"""

import streamlit as st
from pipeline.db import get_supabase_client

st.set_page_config(page_title="Meridian � Sign In", page_icon="", layout="centered")

if "user" not in st.session_state:
    st.session_state["user"] = None
if "session" not in st.session_state:
    st.session_state["session"] = None

invite_token = st.query_params.get("invite", None)
if isinstance(invite_token, list):
    invite_token = invite_token[0] if invite_token else None
if invite_token:
    st.session_state["pending_invite_token"] = invite_token

if st.session_state["user"] is not None:
    st.switch_page("pages/dashboard.py")

supabase = get_supabase_client()

st.markdown(
    """
    <style>
        .stApp {
            background-color: #0E1117;
            color: #FAFAFA;
        }
        [data-baseweb="tab-list"] button {
            color: #FAFAFA;
        }
        [data-baseweb="tab-list"] button[aria-selected="true"] {
            color: #4DB6AC;
        }
        .stButton > button {
            background-color: #4DB6AC;
            color: #0E1117;
            border: 1px solid #4DB6AC;
            font-weight: 600;
        }
        .stButton > button:hover {
            color: #0E1117;
            border-color: #4DB6AC;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("""
   

     
Meridian

     

       Workstream Portfolio Health Dashboard


   
""", unsafe_allow_html=True)

if invite_token:
    st.info("You've been invited to a Meridian workstream. Sign in or create an account to join.")

sign_in_tab, create_account_tab = st.tabs(["Sign In", "Create Account"])

with sign_in_tab:
    email = st.text_input("Email", type="default", key="sign_in_email")
    password = st.text_input("Password", type="password", key="sign_in_password")

    if st.button("Sign In", use_container_width=True):
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            if response and response.user and response.session:
                st.session_state["user"] = response.user
                st.session_state["session"] = response.session
                st.switch_page("pages/dashboard.py")
            else:
                st.error("Invalid email or password. Please try again.")
        except Exception:
            st.error("Invalid email or password. Please try again.")

with create_account_tab:
    display_name = st.text_input("Display name", key="register_display_name")
    register_email = st.text_input("Email", key="register_email")
    register_password = st.text_input("Password", type="password", key="register_password")
    confirm_password = st.text_input("Confirm password", type="password", key="confirm_password")

    if st.button("Create Account", use_container_width=True):
        if not all([display_name, register_email, register_password, confirm_password]):
            st.warning("All fields are required.")
        elif register_password != confirm_password:
            st.warning("Passwords must match.")
        elif len(register_password) < 8:
            st.warning("Password must be at least 8 characters.")
        else:
            try:
                response = supabase.auth.sign_up(
                    {
                        "email": register_email,
                        "password": register_password,
                        "options": {"data": {"display_name": display_name}},
                    }
                )
                st.success(
                    "Account created. Please check your email to confirm your address before signing in."
                )
            except Exception:
                st.error("Could not create account. Please try again.")
