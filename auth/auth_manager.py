"""
Multi-user authentication system for OrbitShow (3.17).

Provides role-based access control with:
- Admin, User, and Viewer roles
- Session management with configurable timeout
- Environment variable configuration for users
- Streamlit integration
"""

import os
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Tuple

import streamlit as st

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User roles with hierarchical permissions."""
    VIEWER = "viewer"       # Read-only access
    USER = "user"           # Can search and task
    ADMIN = "admin"         # Full access including admin panel


# Role hierarchy for permission checking
ROLE_HIERARCHY = {
    UserRole.VIEWER: 0,
    UserRole.USER: 1,
    UserRole.ADMIN: 2,
}


class User:
    """Represents an authenticated user."""

    def __init__(self, username: str, role: UserRole, display_name: str = None):
        self.username = username
        self.role = role if isinstance(role, UserRole) else UserRole(role)
        self.display_name = display_name or username
        self.login_time = datetime.now()

    def has_role(self, required_role: UserRole) -> bool:
        """Check if user has at least the required role."""
        return ROLE_HIERARCHY.get(self.role, -1) >= ROLE_HIERARCHY.get(required_role, 0)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "role": self.role.value,
            "display_name": self.display_name,
            "login_time": self.login_time.isoformat(),
        }


class AuthManager:
    """
    Manages user authentication and session state.
    
    Users are configured via environment variables:
    - ORBITSHOW_ADMIN_USERNAME / ORBITSHOW_ADMIN_PASSWORD (admin)
    - ORBITSHOW_USER_USERNAME / ORBITSHOW_USER_PASSWORD (regular user)
    - ORBITSHOW_VIEWER_USERNAME / ORBITSHOW_VIEWER_PASSWORD (viewer)
    
    Or via a JSON config file at config/users.json:
    {
        "users": [
            {"username": "admin", "password": "hash...", "role": "admin", "display_name": "Admin"},
            {"username": "user1", "password": "hash...", "role": "user", "display_name": "User 1"}
        ]
    }
    """

    def __init__(self, session_timeout_hours: int = 8):
        self.session_timeout = timedelta(hours=session_timeout_hours)
        self._users: Dict[str, Tuple[str, UserRole, str]] = {}  # username -> (password_hash, role, display_name)
        self._load_users_from_env()
        self._load_users_from_config()

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def _load_users_from_env(self):
        """Load users from environment variables."""
        # Admin
        admin_user = os.environ.get("ORBITSHOW_ADMIN_USERNAME")
        admin_pass = os.environ.get("ORBITSHOW_ADMIN_PASSWORD")
        if admin_user and admin_pass:
            self._users[admin_user] = (self._hash_password(admin_pass), UserRole.ADMIN, "Administrator")
            logger.info(f"Loaded admin user: {admin_user}")

        # Regular user
        user_user = os.environ.get("ORBITSHOW_USER_USERNAME")
        user_pass = os.environ.get("ORBITSHOW_USER_PASSWORD")
        if user_user and user_pass:
            self._users[user_user] = (self._hash_password(user_pass), UserRole.USER, user_user)
            logger.info(f"Loaded user: {user_user}")

        # Viewer
        viewer_user = os.environ.get("ORBITSHOW_VIEWER_USERNAME")
        viewer_pass = os.environ.get("ORBITSHOW_VIEWER_PASSWORD")
        if viewer_user and viewer_pass:
            self._users[viewer_user] = (self._hash_password(viewer_pass), UserRole.VIEWER, viewer_user)
            logger.info(f"Loaded viewer: {viewer_user}")

    def _load_users_from_config(self, config_path: str = "config/users.json"):
        """Load users from a JSON configuration file."""
        try:
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_path)
            if not os.path.exists(path):
                return
            with open(path, 'r') as f:
                config = json.load(f)
            for user_config in config.get("users", []):
                username = user_config.get("username")
                password = user_config.get("password")
                role_str = user_config.get("role", "viewer")
                display_name = user_config.get("display_name", username)
                if username and password:
                    try:
                        role = UserRole(role_str)
                    except ValueError:
                        role = UserRole.VIEWER
                    self._users[username] = (self._hash_password(password), role, display_name)
                    logger.info(f"Loaded user from config: {username} ({role.value})")
        except Exception as e:
            logger.warning(f"Failed to load users from config: {e}")

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user. Returns User object on success, None on failure.
        """
        if username not in self._users:
            logger.warning(f"Authentication failed: unknown user '{username}'")
            return None

        stored_hash, role, display_name = self._users[username]
        if hmac.compare_digest(self._hash_password(password), stored_hash):
            user = User(username, role, display_name)
            logger.info(f"User '{username}' authenticated as {role.value}")
            return user

        logger.warning(f"Authentication failed: invalid password for '{username}'")
        return None

    def login(self, username: str, password: str) -> bool:
        """
        Authenticate and store session in Streamlit state.
        Returns True if login successful.
        """
        user = self.authenticate(username, password)
        if user:
            st.session_state.auth_user = user
            st.session_state.auth_authenticated = True
            st.session_state.auth_login_time = datetime.now()
            return True
        return False

    def logout(self):
        """Clear authentication state."""
        st.session_state.auth_user = None
        st.session_state.auth_authenticated = False
        st.session_state.auth_login_time = None
        st.rerun()

    def is_authenticated(self) -> bool:
        """Check if current session is authenticated."""
        if not st.session_state.get("auth_authenticated", False):
            return False

        login_time = st.session_state.get("auth_login_time")
        if login_time and datetime.now() - login_time > self.session_timeout:
            self.logout()
            return False

        return True

    def get_current_user(self) -> Optional[User]:
        """Get the currently authenticated user."""
        if self.is_authenticated():
            return st.session_state.get("auth_user")
        return None

    def has_role(self, required_role: UserRole) -> bool:
        """Check if current user has the required role."""
        user = self.get_current_user()
        if user:
            return user.has_role(required_role)
        return False

    def render_login_form(self):
        """Render the login form in Streamlit."""
        st.markdown("### 🔐 Authentication Required")
        st.markdown("Please log in to access this page.")

        with st.form("auth_login_form"):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")

            col1, col2 = st.columns(2)
            with col1:
                submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
            with col2:
                if st.form_submit_button("Cancel", use_container_width=True):
                    st.switch_page("main.py")

            if submitted:
                if self.login(username, password):
                    st.success(f"✅ Welcome, {st.session_state.auth_user.display_name}!")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password")

    def require_authentication(self, required_role: UserRole = UserRole.VIEWER) -> bool:
        """
        Check authentication and show login form if needed.
        Returns True if authenticated with sufficient role.
        """
        if self.is_authenticated():
            user = self.get_current_user()
            if user and user.has_role(required_role):
                return True
            else:
                st.error(f"❌ Insufficient permissions. Required role: {required_role.value}")
                st.info(f"Your role: {user.role.value if user else 'none'}")
                return False

        self.render_login_form()
        return False


# Global instance for convenience
_auth_manager = None


def get_auth_manager() -> AuthManager:
    """Get or create the global AuthManager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def require_role(role: UserRole):
    """Decorator to require a specific role for a page/function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            auth = get_auth_manager()
            if auth.require_authentication(role):
                return func(*args, **kwargs)
            return None
        return wrapper
    return decorator


def get_current_user() -> Optional[User]:
    """Get the currently authenticated user."""
    return get_auth_manager().get_current_user()
