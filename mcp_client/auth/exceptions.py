"""
MCP認証例外クラス
認証関連のエラーハンドリング
"""


class MCPAuthError(Exception):
    """MCP認証の基底例外クラス"""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        """認証エラーを初期化
        
        Args:
            message: エラーメッセージ
            error_code: エラーコード
            details: 詳細情報
        """
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class TokenExpiredError(MCPAuthError):
    """トークン期限切れエラー"""
    
    def __init__(self, message: str = "Access token has expired"):
        super().__init__(message, error_code="token_expired")


class AuthenticationRequiredError(MCPAuthError):
    """認証が必要エラー"""
    
    def __init__(self, message: str = "Authentication required", auth_url: str = None):
        super().__init__(message, error_code="authentication_required")
        self.auth_url = auth_url


class InvalidTokenError(MCPAuthError):
    """無効なトークンエラー"""
    
    def __init__(self, message: str = "Invalid or malformed token"):
        super().__init__(message, error_code="invalid_token")


class OAuth2Error(MCPAuthError):
    """OAuth 2.1関連エラー"""
    
    def __init__(self, message: str, oauth_error: str = None, error_description: str = None):
        super().__init__(message, error_code=oauth_error)
        self.oauth_error = oauth_error
        self.error_description = error_description


class PKCEError(MCPAuthError):
    """PKCE関連エラー"""
    
    def __init__(self, message: str = "PKCE validation failed"):
        super().__init__(message, error_code="pkce_error")


class ServerDiscoveryError(MCPAuthError):
    """サーバー発見エラー"""
    
    def __init__(self, message: str = "Failed to discover server metadata"):
        super().__init__(message, error_code="discovery_error")


class ClientRegistrationError(MCPAuthError):
    """動的クライアント登録エラー"""
    
    def __init__(self, message: str = "Failed to register client"):
        super().__init__(message, error_code="client_registration_error")


class NetworkError(MCPAuthError):
    """ネットワーク関連エラー"""
    
    def __init__(self, message: str = "Network error occurred"):
        super().__init__(message, error_code="network_error")


class ConfigurationError(MCPAuthError):
    """設定エラー"""
    
    def __init__(self, message: str = "Invalid configuration"):
        super().__init__(message, error_code="configuration_error")