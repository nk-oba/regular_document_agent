"""
Configuration management for the agent application.
Centralizes all environment variables, constants, and configuration settings.
"""
import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class AppConfig:
    """Application configuration class."""
    
    # Basic app settings
    HOST: str = "0.0.0.0"
    PORT: int = int(os.environ.get("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Agent engine parameters
    AGENT_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
    SESSION_DB_URL: str = "sqlite:///./sessions.db"
    ARTIFACT_URL: str = "gs://dev-datap-agent-bucket"
    
    # Session management settings
    USE_UNIFIED_SESSION_MANAGEMENT: bool = os.getenv("USE_UNIFIED_SESSION_MANAGEMENT", "true").lower() == "true"
    SERVE_WEB_INTERFACE: bool = True
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = [
        "http://127.0.0.1:3000", 
        "http://localhost:3000", 
        "http://127.0.0.1:8000", 
        "http://localhost:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ]
    
    # OAuth settings
    GOOGLE_OAUTH_REDIRECT_URI: str = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # Session cleanup intervals (in seconds)
    SESSION_CLEANUP_INTERVAL: int = 3600  # 1 hour
    ORPHANED_ADK_CLEANUP_INTERVAL: int = 3 * 3600  # 3 hours
    ARCHIVED_CHAT_CLEANUP_INTERVAL: int = 24 * 3600  # 24 hours
    ARCHIVED_CHAT_RETENTION_DAYS: int = 90  # 90 days
    
    # Frontend redirect URL
    FRONTEND_REDIRECT_URL: str = "http://localhost:3000"
    
    # File paths
    MCP_ADA_CALLBACK_HTML: str = "mcp_ada_callback.html"
    STATIC_FILES_DIRECTORY: str = "."
    
    @classmethod
    def validate_config(cls) -> None:
        """Validate configuration settings."""
        if cls.GOOGLE_APPLICATION_CREDENTIALS:
            credentials_path = cls.GOOGLE_APPLICATION_CREDENTIALS.replace("/app/", "/app/")
            if not os.path.exists(credentials_path):
                print(f"Warning: Google credentials file not found at {credentials_path}")
        
        if not cls.ALLOWED_ORIGINS:
            raise ValueError("ALLOWED_ORIGINS cannot be empty")
    
    @classmethod
    def is_gcs_enabled(cls) -> bool:
        """Check if GCS artifact service should be used."""
        return (cls.GOOGLE_APPLICATION_CREDENTIALS and 
                os.path.exists(cls.GOOGLE_APPLICATION_CREDENTIALS.replace("/app/", "/app/")))
    
    @classmethod
    def get_gcs_bucket_name(cls) -> str:
        """Get GCS bucket name from artifact URL."""
        return cls.ARTIFACT_URL.replace("gs://", "")

class LogConfig:
    """Logging configuration."""
    LEVEL: str = "INFO"
    FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

class SecurityConfig:
    """Security-related configuration."""
    # Session settings
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "lax"
    
    # Authentication scopes
    OAUTH_SCOPES: List[str] = [
        'openid',
        'email',
        'profile',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents',
        'https://www.googleapis.com/auth/spreadsheets'
    ]

# Initialize and validate configuration
AppConfig.validate_config()