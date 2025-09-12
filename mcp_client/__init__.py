"""
MCP Client Authentication Framework
MCP ADA準拠の統一認証クライアントライブラリ
"""

__version__ = "1.0.0"
__author__ = "AI Solution Team"

from .auth.client import MCPAuthClient
from .auth.exceptions import (
    MCPAuthError,
    TokenExpiredError,
    AuthenticationRequiredError,
    InvalidTokenError
)

__all__ = [
    'MCPAuthClient',
    'MCPAuthError',
    'TokenExpiredError', 
    'AuthenticationRequiredError',
    'InvalidTokenError'
]