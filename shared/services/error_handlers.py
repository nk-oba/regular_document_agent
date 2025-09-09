"""
Unified error handling system for the agent application.
Provides standardized error responses and logging.
"""
import logging
import traceback
from typing import Dict, Any, Optional
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

class ErrorResponse:
    """Standard error response format."""
    
    def __init__(self, success: bool = False, error: str = "", **kwargs):
        self.data = {
            "success": success,
            "error": error,
            **kwargs
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return self.data

class AuthError(Exception):
    """Authentication-related error."""
    pass

class SessionError(Exception):
    """Session management error."""
    pass

class ArtifactError(Exception):
    """Artifact operations error."""
    pass

class DatabaseError(Exception):
    """Database operations error."""
    pass

def handle_auth_error(e: Exception, context: str, user_id: Optional[str] = None, include_traceback: bool = False) -> Dict[str, Any]:
    """
    Handle authentication-related errors.
    
    Args:
        e: Exception that occurred
        context: Context where error occurred
        user_id: Optional user ID for logging
        include_traceback: Whether to include full traceback
        
    Returns:
        Standardized error response
    """
    error_msg = f"{context} error: {str(e)}"
    logger.error(error_msg)
    if user_id:
        logger.error(f"User: {user_id}")
    
    response_data = ErrorResponse(
        success=False,
        error=str(e),
        authenticated=False,
        context=context
    ).to_dict()
    
    if include_traceback:
        tb = traceback.format_exc()
        logger.error(f"Full traceback: {tb}")
        response_data["traceback"] = tb
    
    return response_data

def handle_session_error(e: Exception, context: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Handle session-related errors.
    
    Args:
        e: Exception that occurred
        context: Context where error occurred
        session_id: Optional session ID for logging
        
    Returns:
        Standardized error response
    """
    error_msg = f"{context} error: {str(e)}"
    logger.error(error_msg)
    if session_id:
        logger.error(f"Session: {session_id}")
    
    return ErrorResponse(
        success=False,
        error=str(e),
        context=context,
        session_id=session_id
    ).to_dict()

def handle_database_error(e: Exception, context: str, query: Optional[str] = None) -> Dict[str, Any]:
    """
    Handle database-related errors.
    
    Args:
        e: Exception that occurred
        context: Context where error occurred
        query: Optional SQL query that failed
        
    Returns:
        Standardized error response
    """
    error_msg = f"Database {context} error: {str(e)}"
    logger.error(error_msg)
    if query:
        logger.error(f"Failed query: {query}")
    
    return ErrorResponse(
        success=False,
        error="Database operation failed",
        context=context
    ).to_dict()

def handle_artifact_error(e: Exception, context: str, artifact_name: Optional[str] = None) -> HTTPException:
    """
    Handle artifact-related errors and return HTTPException.
    
    Args:
        e: Exception that occurred
        context: Context where error occurred
        artifact_name: Optional artifact name
        
    Returns:
        HTTPException for FastAPI
    """
    error_msg = f"Artifact {context} error: {str(e)}"
    logger.error(error_msg)
    if artifact_name:
        logger.error(f"Artifact: {artifact_name}")
    
    # Determine appropriate HTTP status code
    if "not found" in str(e).lower():
        status_code = 404
        detail = f"Artifact not found: {artifact_name or 'unknown'}"
    elif "permission" in str(e).lower() or "access" in str(e).lower():
        status_code = 403
        detail = f"Access denied to artifact: {artifact_name or 'unknown'}"
    else:
        status_code = 500
        detail = f"Failed to process artifact: {str(e)}"
    
    return HTTPException(status_code=status_code, detail=detail)

def handle_generic_error(e: Exception, context: str, include_traceback: bool = False) -> Dict[str, Any]:
    """
    Handle generic errors with optional traceback.
    
    Args:
        e: Exception that occurred
        context: Context where error occurred
        include_traceback: Whether to include full traceback in response
        
    Returns:
        Standardized error response
    """
    error_msg = f"{context} error: {str(e)}"
    logger.error(error_msg)
    
    response_data = ErrorResponse(
        success=False,
        error=str(e),
        context=context
    ).to_dict()
    
    if include_traceback:
        tb = traceback.format_exc()
        logger.error(f"Full traceback: {tb}")
        response_data["traceback"] = tb
    
    return response_data

def create_success_response(message: str = "Operation successful", **kwargs) -> Dict[str, Any]:
    """
    Create standardized success response.
    
    Args:
        message: Success message
        **kwargs: Additional data to include
        
    Returns:
        Success response dictionary
    """
    return {
        "success": True,
        "message": message,
        **kwargs
    }

def log_request_info(endpoint: str, user_id: Optional[str] = None, **params):
    """
    Log request information for debugging.
    
    Args:
        endpoint: API endpoint being called
        user_id: Optional user ID
        **params: Request parameters to log
    """
    param_str = ", ".join(f"{k}={v}" for k, v in params.items() if v is not None)
    log_msg = f"Request to {endpoint}"
    if user_id:
        log_msg += f" (user: {user_id})"
    if param_str:
        log_msg += f" with params: {param_str}"
    
    logger.info(log_msg)

def validate_required_params(params: Dict[str, Any], required_fields: list) -> Optional[str]:
    """
    Validate that required parameters are present.
    
    Args:
        params: Parameters to validate
        required_fields: List of required field names
        
    Returns:
        Error message if validation fails, None if successful
    """
    missing_fields = [field for field in required_fields if not params.get(field)]
    
    if missing_fields:
        return f"Missing required parameters: {', '.join(missing_fields)}"
    
    return None

class ErrorLogger:
    """Context manager for error logging with automatic cleanup."""
    
    def __init__(self, context: str, user_id: Optional[str] = None):
        self.context = context
        self.user_id = user_id
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        logger.info(f"Starting {self.context}" + (f" for user {self.user_id}" if self.user_id else ""))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.time() - self.start_time if self.start_time else 0
        
        if exc_type is None:
            logger.info(f"Completed {self.context} in {duration:.2f}s")
        else:
            logger.error(f"Failed {self.context} after {duration:.2f}s: {exc_val}")
        
        return False  # Don't suppress exceptions