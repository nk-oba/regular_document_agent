"""
認証付きHTTPクライアント
自動認証とリトライ機能を持つHTTPトランスポート
"""

import asyncio
from typing import Dict, Any, Optional, Union, Callable
import httpx
import logging
from ..auth.client import MCPAuthClient
from ..auth.exceptions import AuthenticationRequiredError, NetworkError

logger = logging.getLogger(__name__)


class AuthenticatedHTTPClient:
    """認証付きHTTPクライアント
    
    MCPAuthClientと連携して自動認証を行うHTTPクライアント
    """
    
    def __init__(
        self,
        auth_client: MCPAuthClient,
        max_retries: int = 3,
        retry_backoff_factor: float = 1.0
    ):
        """認証付きHTTPクライアントを初期化
        
        Args:
            auth_client: MCP認証クライアント
            max_retries: 最大リトライ回数
            retry_backoff_factor: リトライ間隔の乗数
        """
        self.auth_client = auth_client
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        
        # 認証コールバック
        self._auth_callback: Optional[Callable[[str], None]] = None
        
        logger.debug(f"AuthenticatedHTTPClient initialized for {auth_client.server_url}")
        logger.debug(f"Max retries: {max_retries}, Retry backoff factor: {retry_backoff_factor}")
    
    def set_auth_callback(self, callback: Callable[[str], None]):
        """認証コールバックを設定
        
        Args:
            callback: 認証が必要になった際に呼び出されるコールバック関数
                     引数として認証URLが渡される
        """
        self._auth_callback = callback
    
    async def request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """HTTPリクエストを実行（認証付き）
        
        Args:
            method: HTTPメソッド
            path: リクエストパス（サーバーURLからの相対パス）
            **kwargs: httpxの追加パラメータ
            
        Returns:
            httpx.Response: HTTPレスポンス
            
        Raises:
            AuthenticationRequiredError: 認証が必要で、自動認証もできない場合
            NetworkError: ネットワークエラーが発生した場合
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # デバッグ: リクエスト詳細をログ出力
                full_url = f"{self.auth_client.server_url}{path}"
                logger.debug(f"[MCP REQUEST] {method} {full_url}")
                logger.debug(f"[MCP REQUEST] Headers: {kwargs.get('headers', 'None')}")
                if kwargs.get('json'):
                    logger.debug(f"[MCP REQUEST] JSON Body: {kwargs['json']}")
                if kwargs.get('params'):
                    logger.debug(f"[MCP REQUEST] Query Params: {kwargs['params']}")
                
                # 認証付きリクエストを実行
                response = await self.auth_client.make_authenticated_request(
                    method, path, **kwargs
                )
                
                # デバッグ: レスポンス詳細をログ出力
                logger.debug(f"[MCP RESPONSE] {method} {path} -> Status: {response.status_code}")
                logger.debug(f"[MCP RESPONSE] Headers: {dict(response.headers)}")
                try:
                    response_text = response.text
                    if len(response_text) > 1000:
                        logger.debug(f"[MCP RESPONSE] Body (truncated): {response_text[:1000]}...")
                    else:
                        logger.debug(f"[MCP RESPONSE] Body: {response_text}")
                except Exception as e:
                    logger.debug(f"[MCP RESPONSE] Body read error: {e}")
                
                return response
                
            except AuthenticationRequiredError as e:
                logger.warning(f"Authentication required (attempt {attempt + 1}/{self.max_retries + 1})")
                
                if self._auth_callback and e.auth_url:
                    # 認証コールバックを呼び出し
                    try:
                        await self._handle_auth_callback(e.auth_url)
                        # 認証完了後、次の試行で継続
                        continue
                    except Exception as callback_error:
                        logger.error(f"Auth callback failed: {callback_error}")
                        last_exception = e
                        break
                else:
                    # コールバックが設定されていない場合は即座に例外を投げる
                    raise e
                    
            except NetworkError as e:
                logger.warning(f"Network error (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                last_exception = e
                
                if attempt < self.max_retries:
                    # エクスポネンシャルバックオフでリトライ
                    wait_time = (2 ** attempt) * self.retry_backoff_factor
                    logger.debug(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    break
            
            except Exception as e:
                logger.error(f"Unexpected error during request: {e}")
                last_exception = e
                break
        
        # 全ての試行が失敗した場合
        if last_exception:
            raise last_exception
        else:
            raise NetworkError("Request failed after all retries")
    
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """GETリクエスト"""
        return await self.request('GET', path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """POSTリクエスト"""
        return await self.request('POST', path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """PUTリクエスト"""
        return await self.request('PUT', path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETEリクエスト"""
        return await self.request('DELETE', path, **kwargs)
    
    async def patch(self, path: str, **kwargs) -> httpx.Response:
        """PATCHリクエスト"""
        return await self.request('PATCH', path, **kwargs)
    
    async def _handle_auth_callback(self, auth_url: str):
        """認証コールバックの処理
        
        Args:
            auth_url: 認証URL
        """
        if not self._auth_callback:
            return
        
        try:
            # 同期コールバックか非同期コールバックかを判定
            if asyncio.iscoroutinefunction(self._auth_callback):
                await self._auth_callback(auth_url)
            else:
                self._auth_callback(auth_url)
                
        except Exception as e:
            logger.error(f"Auth callback execution failed: {e}")
            raise
    
    def is_authenticated(self) -> bool:
        """認証状態を確認（同期版）
        
        Returns:
            bool: 認証済みの場合True
        """
        # 同期的にトークンの存在をチェック
        return self.auth_client.token_manager.is_token_valid()
    
    async def is_authenticated_async(self) -> bool:
        """認証状態を確認（非同期版）
        
        Returns:
            bool: 認証済みの場合True
        """
        return await self.auth_client.is_authenticated()
    
    async def revoke_authentication(self) -> bool:
        """認証を取り消し
        
        Returns:
            bool: 成功した場合True
        """
        return await self.auth_client.revoke_authentication()
    
    def get_server_url(self) -> str:
        """サーバーURLを取得
        
        Returns:
            str: サーバーURL
        """
        return self.auth_client.server_url
    
    def get_user_id(self) -> Optional[str]:
        """ユーザーIDを取得
        
        Returns:
            Optional[str]: ユーザーID
        """
        return self.auth_client.user_id


class SimpleAuthenticatedClient:
    """シンプルな認証付きクライアント
    
    基本的な使用ケース向けの簡単なインターフェース
    """
    
    def __init__(
        self,
        server_url: str,
        user_id: Optional[str] = None,
        auth_callback: Optional[Callable[[str], None]] = None
    ):
        """シンプル認証クライアントを初期化
        
        Args:
            server_url: MCPサーバーURL
            user_id: ユーザーID
            auth_callback: 認証コールバック関数
        """
        self.auth_client = MCPAuthClient(server_url, user_id)
        self.http_client = AuthenticatedHTTPClient(self.auth_client)
        
        if auth_callback:
            self.http_client.set_auth_callback(auth_callback)
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        await self.auth_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーの終了"""
        await self.auth_client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """HTTPリクエストを実行"""
        return await self.http_client.request(method, path, **kwargs)
    
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """GETリクエスト"""
        return await self.http_client.get(path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """POSTリクエスト"""
        return await self.http_client.post(path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """PUTリクエスト"""
        return await self.http_client.put(path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETEリクエスト"""
        return await self.http_client.delete(path, **kwargs)
    
    async def patch(self, path: str, **kwargs) -> httpx.Response:
        """PATCHリクエスト"""
        return await self.http_client.patch(path, **kwargs)
    
    def set_auth_callback(self, callback: Callable[[str], None]):
        """認証コールバックを設定"""
        self.http_client.set_auth_callback(callback)
    
    async def is_authenticated(self) -> bool:
        """認証状態を確認"""
        return await self.http_client.is_authenticated_async()
    
    async def revoke_authentication(self) -> bool:
        """認証を取り消し"""
        return await self.http_client.revoke_authentication()