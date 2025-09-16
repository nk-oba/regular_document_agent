"""
HTTP 401インターセプター
自動認証処理とリクエストリトライ
"""

import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable, Union
import httpx
import logging
from ..auth.exceptions import AuthenticationRequiredError

logger = logging.getLogger(__name__)


class Auth401Interceptor:
    """HTTP 401自動処理インターセプター
    
    HTTP 401レスポンスを検出して自動的に認証フローを開始
    """
    
    def __init__(
        self,
        auth_handler: Callable[[], Awaitable[str]],
        auth_completion_handler: Callable[[str, str], Awaitable[bool]],
        max_auth_retries: int = 1
    ):
        """401インターセプターを初期化
        
        Args:
            auth_handler: 認証フロー開始ハンドラー（認証URLを返す）
            auth_completion_handler: 認証完了ハンドラー（auth_code, stateを受け取る）
            max_auth_retries: 認証リトライの最大回数
        """
        self.auth_handler = auth_handler
        self.auth_completion_handler = auth_completion_handler
        self.max_auth_retries = max_auth_retries
        
        # 認証状態の管理
        self._auth_in_progress = False
        self._auth_lock = asyncio.Lock()
        
        logger.debug("Auth401Interceptor initialized")
    
    async def intercept_response(
        self,
        response: httpx.Response,
        request_func: Callable[[], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        """HTTPレスポンスをインターセプト
        
        Args:
            response: 元のHTTPレスポンス
            request_func: 元のリクエストを再実行する関数
            
        Returns:
            httpx.Response: 処理後のHTTPレスポンス
            
        Raises:
            AuthenticationRequiredError: 認証が必要で自動処理もできない場合
        """
        if response.status_code != 401:
            return response
        
        logger.info("HTTP 401 detected, starting automatic authentication")
        
        # 認証の同期処理（複数の401が同時に発生した場合の対策）
        async with self._auth_lock:
            if self._auth_in_progress:
                # 他の処理が認証中の場合は少し待つ
                logger.debug("Authentication already in progress, waiting...")
                await asyncio.sleep(0.5)
                
                # 認証完了後にリクエストを再試行
                return await request_func()
            
            self._auth_in_progress = True
            
        try:
            # 認証フローを実行
            await self._handle_authentication()
            
            # 認証完了後、元のリクエストを再試行
            logger.info("Authentication completed, retrying original request")
            return await request_func()
            
        except Exception as e:
            logger.error(f"Automatic authentication failed: {e}")
            raise AuthenticationRequiredError(f"Authentication failed: {e}")
            
        finally:
            self._auth_in_progress = False
    
    async def _handle_authentication(self):
        """認証処理を実行
        
        Raises:
            AuthenticationRequiredError: 認証に失敗した場合
        """
        try:
            # 認証フロー開始
            auth_url = await self.auth_handler()
            logger.info(f"Authentication URL generated: {auth_url}")
            
            # ここで実際の認証処理を待つ
            # 実装は使用環境に依存するため、コールバック経由で処理
            auth_code, state = await self._wait_for_auth_completion(auth_url)
            
            # 認証完了処理
            success = await self.auth_completion_handler(auth_code, state)
            
            if not success:
                raise AuthenticationRequiredError("Authentication completion failed")
                
        except Exception as e:
            logger.error(f"Authentication handling failed: {e}")
            raise
    
    async def _wait_for_auth_completion(self, auth_url: str) -> tuple[str, str]:
        """認証完了を待機
        
        Args:
            auth_url: 認証URL
            
        Returns:
            tuple[str, str]: (auth_code, state)
            
        Note:
            実際の実装では、この部分は環境に依存します：
            - Webアプリケーション: リダイレクト処理
            - デスクトップアプリ: ローカルサーバーでコールバック受信
            - CLI: ユーザーに手動でコードを入力してもらう
        """
        # プレースホルダー実装
        # 実際の使用では、このメソッドをオーバーライドするか、
        # 認証コールバック機能を使用する
        raise NotImplementedError(
            "Authentication completion waiting must be implemented based on the application environment"
        )


class InteractiveAuth401Interceptor(Auth401Interceptor):
    """インタラクティブ認証インターセプター
    
    CLI環境での対話的認証処理
    """
    
    def __init__(
        self,
        auth_handler: Callable[[], Awaitable[str]],
        auth_completion_handler: Callable[[str, str], Awaitable[bool]]
    ):
        super().__init__(auth_handler, auth_completion_handler)
        self._input_handler: Optional[Callable[[str], Awaitable[str]]] = None
    
    def set_input_handler(self, handler: Callable[[str], Awaitable[str]]):
        """入力ハンドラーを設定
        
        Args:
            handler: ユーザー入力を受け取るハンドラー
        """
        self._input_handler = handler
    
    async def _wait_for_auth_completion(self, auth_url: str) -> tuple[str, str]:
        """CLI環境での認証完了待機
        
        Args:
            auth_url: 認証URL
            
        Returns:
            tuple[str, str]: (auth_code, state)
        """
        if not self._input_handler:
            raise AuthenticationRequiredError(
                f"Please authenticate at: {auth_url}\n"
                "Input handler not configured for interactive authentication"
            )
        
        try:
            print(f"\nAuthentication required. Please visit the following URL:")
            print(f"{auth_url}\n")
            
            # 認証コードの入力を待機
            auth_code = await self._input_handler("Enter the authorization code: ")
            
            # stateは空文字列（簡略化のため）
            # 実際の実装ではURLからstateパラメータを抽出する必要がある
            state = ""
            
            return auth_code.strip(), state
            
        except Exception as e:
            logger.error(f"Interactive authentication failed: {e}")
            raise AuthenticationRequiredError(f"Authentication input failed: {e}")


class CallbackAuth401Interceptor(Auth401Interceptor):
    """コールバック認証インターセプター
    
    Webアプリケーション環境でのコールバック認証処理
    """
    
    def __init__(
        self,
        auth_handler: Callable[[], Awaitable[str]],
        auth_completion_handler: Callable[[str, str], Awaitable[bool]],
        callback_handler: Optional[Callable[[str], Awaitable[tuple[str, str]]]] = None
    ):
        super().__init__(auth_handler, auth_completion_handler)
        self._callback_handler = callback_handler
        self._callback_future: Optional[asyncio.Future] = None
    
    def set_callback_handler(self, handler: Callable[[str], Awaitable[tuple[str, str]]]):
        """コールバックハンドラーを設定
        
        Args:
            handler: 認証コールバックを処理するハンドラー
        """
        self._callback_handler = handler
    
    async def _wait_for_auth_completion(self, auth_url: str) -> tuple[str, str]:
        """コールバック環境での認証完了待機
        
        Args:
            auth_url: 認証URL
            
        Returns:
            tuple[str, str]: (auth_code, state)
        """
        if not self._callback_handler:
            raise AuthenticationRequiredError(
                f"Please authenticate at: {auth_url}\n"
                "Callback handler not configured"
            )
        
        try:
            # コールバックハンドラーに処理を委譲
            return await self._callback_handler(auth_url)
            
        except Exception as e:
            logger.error(f"Callback authentication failed: {e}")
            raise AuthenticationRequiredError(f"Authentication callback failed: {e}")
    
    async def notify_auth_completion(self, auth_code: str, state: str):
        """外部からの認証完了通知を受信
        
        Args:
            auth_code: 認証コード
            state: stateパラメータ
        """
        if self._callback_future and not self._callback_future.done():
            self._callback_future.set_result((auth_code, state))


class AutoRetryInterceptor:
    """自動リトライインターセプター
    
    一時的なエラーに対する自動リトライ機能
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        retry_status_codes: set[int] = None
    ):
        """自動リトライインターセプターを初期化
        
        Args:
            max_retries: 最大リトライ回数
            backoff_factor: バックオフ係数
            retry_status_codes: リトライ対象のHTTPステータスコード
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_status_codes = retry_status_codes or {500, 502, 503, 504, 429}
    
    async def intercept_response(
        self,
        response: httpx.Response,
        request_func: Callable[[], Awaitable[httpx.Response]],
        attempt: int = 0
    ) -> httpx.Response:
        """HTTPレスポンスをインターセプトしてリトライ処理
        
        Args:
            response: HTTPレスポンス
            request_func: リクエスト再実行関数
            attempt: 現在の試行回数
            
        Returns:
            httpx.Response: 処理後のHTTPレスポンス
        """
        if (response.status_code not in self.retry_status_codes or 
            attempt >= self.max_retries):
            return response
        
        # バックオフ待機
        wait_time = (2 ** attempt) * self.backoff_factor
        logger.info(f"Retrying request (attempt {attempt + 1}/{self.max_retries}) after {wait_time}s")
        
        await asyncio.sleep(wait_time)
        
        # リクエスト再実行
        new_response = await request_func()
        
        # 再帰的にインターセプト
        return await self.intercept_response(new_response, request_func, attempt + 1)