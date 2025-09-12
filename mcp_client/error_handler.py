"""
エラーハンドリング強化
包括的なエラー処理とロギング
"""

import asyncio
import logging
import traceback
from typing import Dict, Any, Optional, Callable, Type, Union
from functools import wraps
import httpx

from .auth.exceptions import *

logger = logging.getLogger(__name__)


class ErrorHandler:
    """統合エラーハンドラー
    
    MCP認証関連のエラーを統一的に処理
    """
    
    def __init__(self, log_errors: bool = True, raise_on_unhandled: bool = True):
        """エラーハンドラーを初期化
        
        Args:
            log_errors: エラーをログ出力するか
            raise_on_unhandled: 未処理エラーを再発生させるか
        """
        self.log_errors = log_errors
        self.raise_on_unhandled = raise_on_unhandled
        
        # エラーハンドラーマップ
        self._error_handlers: Dict[Type[Exception], Callable] = {
            TokenExpiredError: self._handle_token_expired,
            AuthenticationRequiredError: self._handle_auth_required,
            InvalidTokenError: self._handle_invalid_token,
            OAuth2Error: self._handle_oauth2_error,
            PKCEError: self._handle_pkce_error,
            ServerDiscoveryError: self._handle_discovery_error,
            ClientRegistrationError: self._handle_registration_error,
            NetworkError: self._handle_network_error,
            ConfigurationError: self._handle_config_error,
            httpx.RequestError: self._handle_httpx_error,
            httpx.HTTPStatusError: self._handle_http_status_error,
        }
        
        # エラー統計
        self._error_counts: Dict[str, int] = {}
    
    def handle_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """エラーを処理
        
        Args:
            error: 発生したエラー
            context: エラーコンテキスト情報
            
        Returns:
            Optional[Any]: 処理結果（ある場合）
        """
        error_type = type(error)
        error_name = error_type.__name__
        
        # エラー統計を更新
        self._error_counts[error_name] = self._error_counts.get(error_name, 0) + 1
        
        # ログ出力
        if self.log_errors:
            self._log_error(error, context)
        
        # 特定のエラーハンドラーを実行
        handler = self._error_handlers.get(error_type)
        if handler:
            try:
                return handler(error, context)
            except Exception as handler_error:
                logger.error(f"Error handler failed: {handler_error}")
                if self.raise_on_unhandled:
                    raise error
        else:
            # 未登録のエラータイプの場合
            logger.warning(f"Unhandled error type: {error_name}")
            if self.raise_on_unhandled:
                raise error
        
        return None
    
    def _log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """エラーをログ出力
        
        Args:
            error: エラー
            context: コンテキスト
        """
        error_msg = f"{type(error).__name__}: {str(error)}"
        
        if context:
            context_str = ", ".join(f"{k}={v}" for k, v in context.items())
            error_msg += f" | Context: {context_str}"
        
        # エラーの重要度に応じてログレベルを調整
        if isinstance(error, (NetworkError, ConfigurationError)):
            logger.error(error_msg, exc_info=True)
        elif isinstance(error, (TokenExpiredError, AuthenticationRequiredError)):
            logger.warning(error_msg)
        else:
            logger.info(error_msg)
    
    def _handle_token_expired(self, error: TokenExpiredError, context: Optional[Dict[str, Any]]) -> str:
        """トークン期限切れエラーの処理"""
        logger.info("Access token expired, refresh required")
        return "refresh_required"
    
    def _handle_auth_required(self, error: AuthenticationRequiredError, context: Optional[Dict[str, Any]]) -> str:
        """認証必須エラーの処理"""
        logger.info("Authentication required")
        if hasattr(error, 'auth_url') and error.auth_url:
            logger.info(f"Authentication URL available: {error.auth_url}")
        return "auth_required"
    
    def _handle_invalid_token(self, error: InvalidTokenError, context: Optional[Dict[str, Any]]) -> str:
        """無効トークンエラーの処理"""
        logger.warning("Invalid token detected, re-authentication required")
        return "reauth_required"
    
    def _handle_oauth2_error(self, error: OAuth2Error, context: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """OAuth2エラーの処理"""
        logger.error(f"OAuth2 error: {error.oauth_error} - {error.error_description}")
        return {
            "type": "oauth2_error",
            "error": error.oauth_error or "unknown",
            "description": error.error_description or str(error)
        }
    
    def _handle_pkce_error(self, error: PKCEError, context: Optional[Dict[str, Any]]) -> str:
        """PKCEエラーの処理"""
        logger.error(f"PKCE validation failed: {error}")
        return "pkce_failed"
    
    def _handle_discovery_error(self, error: ServerDiscoveryError, context: Optional[Dict[str, Any]]) -> str:
        """サーバー発見エラーの処理"""
        logger.error(f"Server discovery failed: {error}")
        return "discovery_failed"
    
    def _handle_registration_error(self, error: ClientRegistrationError, context: Optional[Dict[str, Any]]) -> str:
        """クライアント登録エラーの処理"""
        logger.error(f"Client registration failed: {error}")
        return "registration_failed"
    
    def _handle_network_error(self, error: NetworkError, context: Optional[Dict[str, Any]]) -> str:
        """ネットワークエラーの処理"""
        logger.warning(f"Network error: {error}")
        return "network_error"
    
    def _handle_config_error(self, error: ConfigurationError, context: Optional[Dict[str, Any]]) -> str:
        """設定エラーの処理"""
        logger.error(f"Configuration error: {error}")
        return "config_error"
    
    def _handle_httpx_error(self, error: httpx.RequestError, context: Optional[Dict[str, Any]]) -> str:
        """HTTPXリクエストエラーの処理"""
        logger.warning(f"HTTP request error: {error}")
        return "request_error"
    
    def _handle_http_status_error(self, error: httpx.HTTPStatusError, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """HTTPステータスエラーの処理"""
        logger.warning(f"HTTP {error.response.status_code} error: {error}")
        return {
            "type": "http_status_error",
            "status_code": error.response.status_code,
            "response_text": error.response.text if hasattr(error.response, 'text') else str(error)
        }
    
    def register_error_handler(self, error_type: Type[Exception], handler: Callable):
        """カスタムエラーハンドラーを登録
        
        Args:
            error_type: 処理するエラータイプ
            handler: ハンドラー関数
        """
        self._error_handlers[error_type] = handler
        logger.debug(f"Registered custom error handler for {error_type.__name__}")
    
    def get_error_statistics(self) -> Dict[str, int]:
        """エラー統計を取得
        
        Returns:
            Dict[str, int]: エラータイプ別の発生回数
        """
        return self._error_counts.copy()
    
    def clear_error_statistics(self):
        """エラー統計をクリア"""
        self._error_counts.clear()


def with_error_handling(
    handler: Optional[ErrorHandler] = None,
    ignore_errors: tuple = (),
    reraise_errors: tuple = ()
):
    """エラーハンドリングデコレータ
    
    Args:
        handler: 使用するエラーハンドラー
        ignore_errors: 無視するエラータイプ
        reraise_errors: 再発生させるエラータイプ
    """
    if handler is None:
        handler = ErrorHandler()
    
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if isinstance(e, ignore_errors):
                        logger.debug(f"Ignoring error: {e}")
                        return None
                    
                    if isinstance(e, reraise_errors):
                        raise
                    
                    context = {
                        'function': func.__name__,
                        'args_count': len(args),
                        'kwargs_keys': list(kwargs.keys())
                    }
                    
                    result = handler.handle_error(e, context)
                    return result
            
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if isinstance(e, ignore_errors):
                        logger.debug(f"Ignoring error: {e}")
                        return None
                    
                    if isinstance(e, reraise_errors):
                        raise
                    
                    context = {
                        'function': func.__name__,
                        'args_count': len(args),
                        'kwargs_keys': list(kwargs.keys())
                    }
                    
                    result = handler.handle_error(e, context)
                    return result
            
            return sync_wrapper
    
    return decorator


class CircuitBreaker:
    """サーキットブレーカー実装
    
    連続するエラーを検出してリクエストを一時停止
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        expected_exception: Type[Exception] = Exception
    ):
        """サーキットブレーカーを初期化
        
        Args:
            failure_threshold: 失敗閾値
            reset_timeout: リセットタイムアウト（秒）
            expected_exception: 監視する例外タイプ
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half_open
    
    def call(self, func, *args, **kwargs):
        """関数をサーキットブレーカー経由で実行
        
        Args:
            func: 実行する関数
            *args: 関数の引数
            **kwargs: 函数のキーワード引数
            
        Returns:
            関数の実行結果
            
        Raises:
            CircuitBreakerOpenError: サーキットが開いている場合
        """
        if self.state == 'open':
            if self._should_attempt_reset():
                self.state = 'half_open'
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """リセット試行すべきかチェック"""
        import time
        return time.time() - self.last_failure_time >= self.reset_timeout
    
    def _on_success(self):
        """成功時の処理"""
        self.failure_count = 0
        self.state = 'closed'
    
    def _on_failure(self):
        """失敗時の処理"""
        import time
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'open'


class CircuitBreakerOpenError(Exception):
    """サーキットブレーカーが開いている時のエラー"""
    pass


def with_circuit_breaker(
    failure_threshold: int = 5,
    reset_timeout: int = 60,
    expected_exception: Type[Exception] = Exception
):
    """サーキットブレーカーデコレータ
    
    Args:
        failure_threshold: 失敗閾値
        reset_timeout: リセットタイムアウト
        expected_exception: 監視する例外タイプ
    """
    circuit_breaker = CircuitBreaker(failure_threshold, reset_timeout, expected_exception)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return circuit_breaker.call(func, *args, **kwargs)
        return wrapper
    
    return decorator


# グローバルエラーハンドラーインスタンス
default_error_handler = ErrorHandler()


def handle_mcp_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """MCP関連エラーを処理する便利関数
    
    Args:
        error: 発生したエラー
        context: エラーコンテキスト
        
    Returns:
        Optional[Any]: 処理結果
    """
    return default_error_handler.handle_error(error, context)