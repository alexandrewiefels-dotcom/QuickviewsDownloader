# ============================================================================
# FILE: admin_auth.py – Simple admin authentication for OrbitShow
# ============================================================================
import streamlit as st
import hashlib
import hmac
from datetime import datetime, timedelta

# Admin credentials (in production, use environment variables or database)
# These are hashed for basic security - change these values!
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("OrbitShow2024!".encode()).hexdigest()

# Session timeout in hours
SESSION_TIMEOUT_HOURS = 8


def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, password_hash):
    """Verify a password against its hash"""
    return hmac.compare_digest(hash_password(password), password_hash)


def is_authenticated():
    """Check if the admin is currently authenticated"""
    if 'admin_authenticated' not in st.session_state:
        return False
    
    if not st.session_state.admin_authenticated:
        return False
    
    # Check session timeout
    if 'admin_login_time' in st.session_state:
        login_time = st.session_state.admin_login_time
        if datetime.now() - login_time > timedelta(hours=SESSION_TIMEOUT_HOURS):
            # Session expired
            st.session_state.admin_authenticated = False
            st.session_state.admin_login_time = None
            return False
    
    return True


def authenticate(username, password):
    """Authenticate admin user"""
    if username == ADMIN_USERNAME and verify_password(password, ADMIN_PASSWORD_HASH):
        st.session_state.admin_authenticated = True
        st.session_state.admin_login_time = datetime.now()
        return True
    return False


def logout():
    """Logout admin user"""
    st.session_state.admin_authenticated = False
    st.session_state.admin_login_time = None
    st.rerun()


def is_admin():
    """Check if current user is admin (authenticated)"""
    return is_authenticated()


def render_login_form():
    """Render the admin login form"""
    st.markdown("### 🔐 Admin Access Required")
    st.markdown("Please enter your credentials to access the admin dashboard.")
    
    with st.form("admin_login_form"):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        with col2:
            if st.form_submit_button("Cancel", use_container_width=True):
                st.switch_page("main.py")
        
        if submitted:
            if authenticate(username, password):
                st.success("✅ Login successful! Redirecting...")
                st.rerun()
            else:
                st.error("❌ Invalid username or password")


def authenticate_admin():
    """
    Check admin authentication and show login form if not authenticated.
    Returns True if authenticated, False otherwise.
    """
    if is_authenticated():
        return True
    
    render_login_form()
    return False


# Optional: Environment variable support for production
import os
def get_admin_credentials_from_env():
    """Get admin credentials from environment variables (for production)"""
    env_username = os.environ.get('ORBITSHOW_ADMIN_USERNAME')
    env_password = os.environ.get('ORBITSHOW_ADMIN_PASSWORD')
    
    if env_username and env_password:
        global ADMIN_USERNAME, ADMIN_PASSWORD_HASH
        ADMIN_USERNAME = env_username
        ADMIN_PASSWORD_HASH = hash_password(env_password)
        return True
    return False


# Try to load from environment on module import
get_admin_credentials_from_env()
