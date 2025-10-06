"""
Credential Manager for MCP ADA
Manages OAuth2 tokens using ADK SessionService
"""
import logging
from typing import Optional, Dict, Union
from google.adk.sessions import (
    DatabaseSessionService,
    InMemorySessionService,
    BaseSessionService
)

from ..auth.mcp_ada_adk_auth import TOKEN_CACHE_KEY, REFRESH_TOKEN_CACHE_KEY

logger = logging.getLogger(__name__)


class MCPADACredentialManager:
    """
    Manages MCP ADA credentials using ADK SessionService

    This class provides a clean interface for storing and retrieving
    OAuth2 tokens in ADK session state.
    """

    def __init__(self, session_service: Union[DatabaseSessionService, InMemorySessionService, BaseSessionService]):
        """
        Initialize the credential manager

        Args:
            session_service: ADK SessionService instance
        """
        self.session_service = session_service

    async def store_tokens(
        self,
        session_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None
    ) -> bool:
        """
        Store OAuth2 tokens in ADK session state

        Args:
            session_id: ADK session identifier
            access_token: OAuth2 access token
            refresh_token: Optional OAuth2 refresh token
            expires_in: Optional token expiry time in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session = await self.session_service.get_session(session_id)

            if not session:
                logger.error(f"Session {session_id} not found")
                return False

            # Store tokens in session state
            session.state[TOKEN_CACHE_KEY] = access_token

            if refresh_token:
                session.state[REFRESH_TOKEN_CACHE_KEY] = refresh_token

            if expires_in:
                session.state["mcp_ada_expires_in"] = expires_in

            await self.session_service.update_session(session)
            logger.info(f"Stored MCP ADA tokens for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to store MCP ADA tokens for session {session_id}: {e}")
            return False

    async def get_access_token(self, session_id: str) -> Optional[str]:
        """
        Retrieve access token from ADK session state

        Args:
            session_id: ADK session identifier

        Returns:
            str: Access token if available, None otherwise
        """
        try:
            session = await self.session_service.get_session(session_id)

            if not session:
                logger.warning(f"Session {session_id} not found")
                return None

            return session.state.get(TOKEN_CACHE_KEY)

        except Exception as e:
            logger.error(f"Failed to get access token for session {session_id}: {e}")
            return None

    async def get_refresh_token(self, session_id: str) -> Optional[str]:
        """
        Retrieve refresh token from ADK session state

        Args:
            session_id: ADK session identifier

        Returns:
            str: Refresh token if available, None otherwise
        """
        try:
            session = await self.session_service.get_session(session_id)

            if not session:
                logger.warning(f"Session {session_id} not found")
                return None

            return session.state.get(REFRESH_TOKEN_CACHE_KEY)

        except Exception as e:
            logger.error(f"Failed to get refresh token for session {session_id}: {e}")
            return None

    async def get_tokens(self, session_id: str) -> Dict[str, Optional[str]]:
        """
        Retrieve all MCP ADA tokens from session state

        Args:
            session_id: ADK session identifier

        Returns:
            dict: Dictionary containing access_token, refresh_token, and expires_in
        """
        try:
            session = await self.session_service.get_session(session_id)

            if not session:
                logger.warning(f"Session {session_id} not found")
                return {}

            return {
                "access_token": session.state.get(TOKEN_CACHE_KEY),
                "refresh_token": session.state.get(REFRESH_TOKEN_CACHE_KEY),
                "expires_in": session.state.get("mcp_ada_expires_in")
            }

        except Exception as e:
            logger.error(f"Failed to get tokens for session {session_id}: {e}")
            return {}

    async def clear_tokens(self, session_id: str) -> bool:
        """
        Clear MCP ADA tokens from session state

        Args:
            session_id: ADK session identifier

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session = await self.session_service.get_session(session_id)

            if not session:
                logger.warning(f"Session {session_id} not found")
                return False

            # Remove token keys from state
            session.state.pop(TOKEN_CACHE_KEY, None)
            session.state.pop(REFRESH_TOKEN_CACHE_KEY, None)
            session.state.pop("mcp_ada_expires_in", None)

            await self.session_service.update_session(session)
            logger.info(f"Cleared MCP ADA tokens for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to clear tokens for session {session_id}: {e}")
            return False

    async def is_authenticated(self, session_id: str) -> bool:
        """
        Check if session has valid MCP ADA authentication

        Args:
            session_id: ADK session identifier

        Returns:
            bool: True if authenticated, False otherwise
        """
        access_token = await self.get_access_token(session_id)
        return access_token is not None and len(access_token) > 0
