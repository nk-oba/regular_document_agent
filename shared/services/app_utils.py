"""
Common utility functions for the agent application.
Contains reusable functions for MIME type detection, hashing, and other common operations.
"""
import hashlib
import sqlite3
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
from shared.core.config import AppConfig

logger = logging.getLogger(__name__)

def get_mime_type_from_extension(filename: str) -> str:
    """
    Get MIME type from file extension.
    
    Args:
        filename: The filename to analyze
        
    Returns:
        MIME type string
    """
    extension = filename.lower().split('.')[-1] if '.' in filename else ''
    
    mime_types = {
        'csv': 'text/csv',
        'txt': 'text/plain',
        'json': 'application/json',
        'pdf': 'application/pdf',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'xls': 'application/vnd.ms-excel',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'ppt': 'application/vnd.ms-powerpoint',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'svg': 'image/svg+xml',
        'html': 'text/html',
        'xml': 'application/xml',
        'zip': 'application/zip',
        'tar': 'application/x-tar',
        'gz': 'application/gzip'
    }
    
    return mime_types.get(extension, 'application/octet-stream')

def generate_adk_user_id(email: str) -> str:
    """
    Generate stable ADK user ID from email.
    
    Args:
        email: User's email address
        
    Returns:
        16-character hash string
    """
    if not email:
        return "anonymous"
    
    normalized_email = email.strip().lower()
    hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
    return hash_object.hexdigest()[:16]

def validate_email(email: str) -> bool:
    """
    Basic email validation.
    
    Args:
        email: Email string to validate
        
    Returns:
        True if email appears valid, False otherwise
    """
    if not email or '@' not in email:
        return False
    
    parts = email.split('@')
    return len(parts) == 2 and all(part.strip() for part in parts)

@contextmanager
def get_db_connection(db_url: Optional[str] = None):
    """
    Context manager for database connections.
    
    Args:
        db_url: Database URL (defaults to AppConfig.SESSION_DB_URL)
        
    Yields:
        sqlite3.Connection: Database connection
    """
    if db_url is None:
        db_url = AppConfig.SESSION_DB_URL
    
    # Remove sqlite:/// prefix if present
    db_path = db_url.replace('sqlite:///', '')
    
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def prepare_file_data(file_data: Any) -> bytes:
    """
    Convert various data types to bytes for file operations.
    
    Args:
        file_data: Data to convert (str, bytes, or other)
        
    Returns:
        Data as bytes
        
    Raises:
        ValueError: If data cannot be converted to bytes
    """
    if file_data is None:
        raise ValueError("No file data provided")
    
    if isinstance(file_data, bytes):
        return file_data
    elif isinstance(file_data, str):
        return file_data.encode('utf-8')
    elif isinstance(file_data, bytearray):
        return bytes(file_data)
    else:
        # Try to convert to string first, then to bytes
        return str(file_data).encode('utf-8')

def safe_dict_get(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Safely get value from dictionary with logging.
    
    Args:
        data: Dictionary to search
        key: Key to look for
        default: Default value if key not found
        
    Returns:
        Value from dictionary or default
    """
    try:
        return data.get(key, default)
    except AttributeError:
        logger.warning(f"Expected dict but got {type(data)} when accessing key '{key}'")
        return default

def log_function_call(func_name: str, **kwargs) -> None:
    """
    Log function call with parameters (for debugging).
    
    Args:
        func_name: Name of the function being called
        **kwargs: Function parameters to log
    """
    if AppConfig.DEBUG:
        params = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        logger.debug(f"Calling {func_name}({params})")

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe usage.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    
    # Remove or replace unsafe characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove leading/trailing whitespace and dots
    filename = filename.strip('. ')
    
    # Ensure filename is not empty
    if not filename:
        filename = "untitled"
    
    return filename

def get_current_timestamp() -> int:
    """
    Get current Unix timestamp.
    
    Returns:
        Current timestamp as integer
    """
    import time
    return int(time.time())

def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"