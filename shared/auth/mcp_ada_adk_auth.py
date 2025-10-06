"""
MCP ADA Authentication for Google ADK
Provides ADK-standard authentication components for MCP ADA OAuth2 integration
"""
import logging
from typing import Optional, Dict, Any
from google.adk.auth import AuthCredential, AuthCredentialTypes, OAuth2Auth, AuthScheme

from .mcp_ada_auth import get_mcp_ada_auth_manager

logger = logging.getLogger(__name__)

# Token cache key for ADK session state
TOKEN_CACHE_KEY = "mcp_ada_access_token"
REFRESH_TOKEN_CACHE_KEY = "mcp_ada_refresh_token"


def create_mcp_ada_auth_scheme() -> Dict[str, Any]:
    """
    Create ADK-standard AuthScheme for MCP ADA OAuth2 with PKCE

    Returns:
        dict: ADK authentication scheme configuration for public client with PKCE
    """
    # Return a simple dict configuration for OAuth2 with PKCE
    # ADK will handle the authentication flow
    return {
        'type': 'oauth2',
        'authorization_endpoint': "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize",
        'token_endpoint': "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token",
        'scopes': ['mcp:reports', 'mcp:properties'],
        'token_endpoint_auth_method': 'none'  # PKCEパブリッククライアント、client_secret不要
    }


def create_mcp_ada_auth_credential(user_id: str) -> Optional[AuthCredential]:
    """
    Create user-specific ADK AuthCredential for MCP ADA

    Args:
        user_id: User identifier for credential lookup

    Returns:
        AuthCredential: ADK authentication credential or None if client not registered
    """
    try:
        auth_manager = get_mcp_ada_auth_manager(user_id)

        # Ensure client is registered
        if not auth_manager._ensure_client_registered():
            logger.error(f"Failed to register MCP ADA client for user {user_id}")
            return None

        # PKCEパブリッククライアントの場合、client_secretは実際には不要だが
        # ADKフレームワークの検証要件を満たすためダミー値を設定
        # 実際のトークン交換ではcode_verifierのみが使用される
        client_secret_value = auth_manager.client_secret if auth_manager.client_secret else "pkce-public-client-no-secret"

        return AuthCredential(
            auth_type=AuthCredentialTypes.OPEN_ID_CONNECT,
            oauth2=OAuth2Auth(
                client_id=auth_manager.client_id,
                client_secret=client_secret_value
            )
        )
    except Exception as e:
        logger.error(f"Failed to create MCP ADA auth credential for user {user_id}: {e}")
        return None


def get_mcp_ada_token_from_state(state: dict) -> Optional[str]:
    """
    Extract MCP ADA access token from ADK session state

    Args:
        state: ADK session state dictionary

    Returns:
        str: Access token if available, None otherwise
    """
    return state.get(TOKEN_CACHE_KEY)


def is_mcp_ada_authenticated(state: dict) -> bool:
    """
    Check if user has valid MCP ADA authentication in session state

    Args:
        state: ADK session state dictionary

    Returns:
        bool: True if authenticated, False otherwise
    """
    token = get_mcp_ada_token_from_state(state)
    return token is not None and len(token) > 0