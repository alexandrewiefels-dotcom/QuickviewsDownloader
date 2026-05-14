"""
Authentication module for OrbitShow (3.17).

Provides multi-user authentication with:
- Role-based access (admin, user, viewer)
- Session management with configurable timeout
- Environment variable configuration
- Login form rendering
"""

from auth.auth_manager import AuthManager, UserRole, require_role, get_current_user

__all__ = ["AuthManager", "UserRole", "require_role", "get_current_user"]
