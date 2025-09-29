"""
Session utility functions for API endpoints.

This module contains helper functions for processing session data,
extracting user messages, and formatting session information.
"""

import datetime
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def extract_first_user_message(detailed_session) -> Optional[Dict[str, Any]]:
    """
    Extract the first user message from session events.

    Args:
        detailed_session: Session object with events attribute

    Returns:
        Dict containing first user message info or None if not found
    """
    if not (hasattr(detailed_session, 'events') and detailed_session.events):
        return None

    for event in detailed_session.events:
        if not (hasattr(event, 'author') and event.author == 'user'):
            continue
        if not (hasattr(event, 'content') and event.content):
            continue

        try:
            text_content = ""
            if hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_content += part.text

            if text_content:
                timestamp = getattr(event, 'timestamp', None)
                return {
                    "content": text_content[:100],
                    "role": event.author,
                    "timestamp": timestamp
                }
        except Exception as e:
            logger.warning(f"Failed to extract message content: {e}")
            continue

    return None


def format_creation_time(last_update_time: Optional[float]) -> Optional[str]:
    """
    Convert unix timestamp to ISO format.

    Args:
        last_update_time: Unix timestamp or None

    Returns:
        ISO format datetime string or None
    """
    if not last_update_time:
        return None

    try:
        return datetime.datetime.fromtimestamp(last_update_time).isoformat()
    except Exception:
        return None


async def get_session_details(
    session_service,
    app_name: str,
    user_id: str,
    session
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Get detailed session information and format it.

    Args:
        session_service: DatabaseSessionService instance
        app_name: Application name
        user_id: User ID
        session: Session object or tuple

    Returns:
        Tuple of (session_dict, first_message)
    """
    # Get detailed session information using get_session
    detailed_session = None
    if hasattr(session, 'id'):
        try:
            detailed_session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session.id
            )
        except Exception as e:
            logger.warning(f"Failed to get detailed session {session.id}: {e}")
            detailed_session = session

    if detailed_session:
        created_at = format_creation_time(getattr(detailed_session, 'last_update_time', None))
        first_message = extract_first_user_message(detailed_session)

        return {
            "session_id": detailed_session.id,
            "user_id": detailed_session.user_id,
            "app_name": detailed_session.app_name,
            "created_at": created_at,
            "messages": []
        }, first_message

    elif isinstance(session, tuple):
        return {
            "session_id": session[0] if len(session) > 0 else None,
            "user_id": session[1] if len(session) > 1 else None,
            "app_name": session[2] if len(session) > 2 else None,
            "created_at": session[3] if len(session) > 3 else None,
            "messages": []
        }, None

    else:
        return {
            "session_id": getattr(session, 'id', None),
            "user_id": getattr(session, 'user_id', None),
            "app_name": getattr(session, 'app_name', None),
            "created_at": None,
            "messages": []
        }, None