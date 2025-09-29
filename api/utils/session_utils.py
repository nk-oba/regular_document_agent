"""
Session utility functions for API endpoints.

This module contains helper functions for processing session data,
extracting user messages, and formatting session information.
"""

import datetime
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)


def generate_session_title(first_message_content: Optional[str], session_id: str) -> str:
    """
    Generate a meaningful title from the first message content.

    Args:
        first_message_content: Content of the first user message
        session_id: Session ID for fallback

    Returns:
        Generated title string
    """
    if not first_message_content:
        return f"Session {session_id[:8]}"

    # Clean and truncate content for title
    cleaned_content = first_message_content.strip()

    prefixes_to_remove = ["こんにちは", "お疲れさま", "お世話になっております"]
    for prefix in prefixes_to_remove:
        if cleaned_content.startswith(prefix):
            cleaned_content = cleaned_content[len(prefix):].strip()

    if len(cleaned_content) > 50:
        cleaned_content = cleaned_content[:47] + "..."

    return cleaned_content if cleaned_content else f"Session {session_id[:8]}"


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


def extract_last_message(detailed_session) -> Optional[Dict[str, Any]]:
    """
    Extract the last message from session events.

    Args:
        detailed_session: Session object with events attribute

    Returns:
        Dict containing last message info or None if not found
    """
    if not (hasattr(detailed_session, 'events') and detailed_session.events):
        return None

    for event in reversed(detailed_session.events):
        if hasattr(event, 'content') and event.content:
            try:
                text_content = ""
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_content += part.text

                if text_content:
                    timestamp = getattr(event, 'timestamp', None)
                    author = getattr(event, 'author', 'unknown')
                    return {
                        "content": text_content[:100],  # 最初の100文字
                        "role": author,
                        "timestamp": timestamp
                    }
            except Exception as e:
                logger.warning(f"Failed to extract last message content: {e}")
                continue

    return None


def get_message_count(detailed_session) -> int:
    """
    Count the number of messages in a session.

    Args:
        detailed_session: Session object with events attribute

    Returns:
        Number of messages in the session
    """
    if not (hasattr(detailed_session, 'events') and detailed_session.events):
        return 0

    count = 0
    for event in detailed_session.events:
        if hasattr(event, 'content') and event.content:
            try:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            count += 1
                            break  # Count only once per event
            except Exception:
                continue

    return count


def format_timestamp(timestamp: Optional[float]) -> Optional[str]:
    """
    Convert unix timestamp to ISO format with Japan Standard Time (JST).

    Args:
        timestamp: Unix timestamp or None

    Returns:
        ISO format datetime string in JST timezone or None
    """
    if not timestamp:
        return None

    try:
        # Japan Standard Time (UTC+9)
        jst_timezone = datetime.timezone(datetime.timedelta(hours=9))
        dt = datetime.datetime.fromtimestamp(timestamp, tz=jst_timezone)
        return dt.isoformat()
    except Exception:
        return None


def format_creation_time(last_update_time: Optional[float]) -> Optional[str]:
    """
    Convert unix timestamp to ISO format (backward compatibility).

    Args:
        last_update_time: Unix timestamp or None

    Returns:
        ISO format datetime string or None
    """
    return format_timestamp(last_update_time)


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
        last_message = extract_last_message(detailed_session)
        message_count = get_message_count(detailed_session)

        first_message_content = first_message.get('content') if first_message else None
        title = generate_session_title(first_message_content, detailed_session.id)

        return {
            "session_id": detailed_session.id,
            "user_id": detailed_session.user_id,
            "app_name": detailed_session.app_name,
            "created_at": created_at,
            "updated_at": format_timestamp(getattr(detailed_session, 'last_update_time', None)),
            "title": title,
            "message_count": message_count,
            "status": "active",  # Default status, can be enhanced later
            "messages": []
        }, first_message, last_message

    elif isinstance(session, tuple):
        session_id = session[0] if len(session) > 0 else None
        return {
            "session_id": session_id,
            "user_id": session[1] if len(session) > 1 else None,
            "app_name": session[2] if len(session) > 2 else None,
            "created_at": session[3] if len(session) > 3 else None,
            "updated_at": session[3] if len(session) > 3 else None,
            "title": f"Session {session_id[:8]}" if session_id else "Unknown Session",
            "message_count": 0,
            "status": "active",
            "messages": []
        }, None, None

    else:
        session_id = getattr(session, 'id', None)
        return {
            "session_id": session_id,
            "user_id": getattr(session, 'user_id', None),
            "app_name": getattr(session, 'app_name', None),
            "created_at": None,
            "updated_at": None,
            "title": f"Session {session_id[:8]}" if session_id else "Unknown Session",
            "message_count": 0,
            "status": "active",
            "messages": []
        }, None, None