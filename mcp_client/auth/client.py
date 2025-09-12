"""
MCP認証クライアント
OAuth 2.1 + PKCE準拠の統一認証クライアント
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from urllib.parse import urlencode, parse_qs, urlparse
import httpx
import logging

from .pkce_handler import PKCEHandler
from .token_manager import TokenManager
from .discovery import ServerDiscovery
from .exceptions import *
from ..utils.storage import SecureStorage
from ..config.settings import MCPClientConfig, ServerConfig, get_default_config

logger = logging.getLogger(__name__)


class MCPAuthClient:
    """MCP ADA準拠の統一認証クライアント
    
    OAuth 2.1 + PKCE、動的クライアント登録、HTTP 401自動処理を提供
    """
    
    def __init__(
        self,
        server_url: str,
        user_id: Optional[str] = None,
        config: Optional[MCPClientConfig] = None,
        storage: Optional[SecureStorage] = None
    ):
        """認証クライアントを初期化
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID（マルチユーザー対応）
            config: クライアント設定
            storage: セキュアストレージ
        """
        self.server_url = server_url.rstrip('/')
        self.user_id = user_id
        self.config = config or get_default_config()
        self.storage = storage or SecureStorage()
        
        # コンポーネント初期化
        self.pkce_handler = PKCEHandler()
        self.token_manager = TokenManager(self.server_url, self.user_id, self.storage)
        self.discovery = ServerDiscovery(
            timeout=self.config.timeout,
            verify_ssl=self.config.validate_ssl
        )
        
        # 内部状態
        self._server_metadata: Optional[Dict[str, Any]] = None
        self._client_info: Optional[Dict[str, Any]] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"MCPAuthClient initialized for {self.server_url} (user: {self.user_id})")
    
    async def __aenter__(self):
        """非同期コンテキストマネージャーのエントリー"""
        await self._ensure_http_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """非同期コンテキストマネージャーの終了"""
        await self.close()
    
    async def close(self):
        """リソースのクリーンアップ"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def _ensure_http_client(self):
        """HTTPクライアントの確保"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                verify=self.config.validate_ssl
            )
    
    async def get_access_token(self) -> Optional[str]:
        """有効なアクセストークンを取得
        
        Returns:
            Optional[str]: アクセストークン、存在しない場合はNone
        """
        access_token = self.token_manager.get_access_token()
        
        if access_token:
            logger.debug("Using existing valid access token")
            return access_token
        
        # リフレッシュトークンでの更新を試行
        refresh_token = self.token_manager.get_refresh_token()
        if refresh_token:
            logger.info("Attempting token refresh")
            try:
                new_tokens = await self._refresh_access_token(refresh_token)
                if new_tokens:
                    self.token_manager.store_tokens(new_tokens)
                    return new_tokens.get('access_token')
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}")
        
        logger.debug("No valid access token available")
        return None
    
    async def is_authenticated(self) -> bool:
        """認証済みかチェック
        
        Returns:
            bool: 有効なアクセストークンがある場合True
        """
        return await self.get_access_token() is not None
    
    async def start_authentication_flow(self) -> str:
        """認証フローを開始してauthorization URLを取得
        
        Returns:
            str: 認証URL
            
        Raises:
            AuthenticationRequiredError: 認証フローの開始に失敗した場合
        """
        try:
            # サーバーメタデータを取得
            await self._ensure_server_metadata()
            
            # クライアント登録を確保
            await self._ensure_client_registered()
            
            # PKCEパラメータを生成
            code_verifier, code_challenge, state = self.pkce_handler.generate_pkce_params()
            
            # 認証URLを構築
            auth_url = await self._build_authorization_url(code_challenge, state)
            
            logger.info("Authentication flow started")
            logger.debug(f"Authorization URL: {auth_url}")
            
            return auth_url
            
        except Exception as e:
            logger.error(f"Failed to start authentication flow: {e}")
            raise AuthenticationRequiredError(f"Authentication flow failed: {e}")
    
    async def complete_authentication_flow(self, authorization_code: str, state: str) -> bool:
        """認証フローを完了してトークンを取得
        
        Args:
            authorization_code: 認証サーバーから返されたauthorization code
            state: 認証サーバーから返されたstate parameter
            
        Returns:
            bool: 認証成功の場合True
            
        Raises:
            OAuth2Error: OAuth 2.1エラーが発生した場合
            PKCEError: PKCE検証に失敗した場合
        """
        try:
            # State parameter検証
            if not self.pkce_handler.validate_state(state):
                raise PKCEError("State parameter validation failed")
            
            # Authorization codeをaccess tokenに交換
            token_data = await self._exchange_authorization_code(authorization_code)
            
            if token_data:
                # トークンを保存
                self.token_manager.store_tokens(token_data)
                
                # PKCEパラメータをクリア
                self.pkce_handler.clear()
                
                logger.info("Authentication completed successfully")
                return True
            else:
                logger.error("Failed to obtain access token")
                return False
                
        except Exception as e:
            logger.error(f"Failed to complete authentication flow: {e}")
            raise
    
    async def make_authenticated_request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """認証付きHTTPリクエストを実行
        
        Args:
            method: HTTPメソッド
            path: リクエストパス
            **kwargs: httpxの追加パラメータ
            
        Returns:
            httpx.Response: HTTPレスポンス
            
        Raises:
            AuthenticationRequiredError: 認証が必要な場合
            NetworkError: ネットワークエラーが発生した場合
        """
        await self._ensure_http_client()
        
        # アクセストークンを取得
        access_token = await self.get_access_token()
        
        # 認証ヘッダーを追加
        headers = kwargs.get('headers', {})
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        kwargs['headers'] = headers
        
        # URL構築
        url = f"{self.server_url}{path}"
        
        try:
            response = await self._http_client.request(method, url, **kwargs)
            
            # HTTP 401の処理
            if response.status_code == 401:
                logger.warning("Received HTTP 401, authentication required")
                raise AuthenticationRequiredError(
                    "Authentication required",
                    auth_url=await self.start_authentication_flow()
                )
            
            return response
            
        except httpx.RequestError as e:
            logger.error(f"Network error: {e}")
            raise NetworkError(f"Request failed: {e}")
    
    async def revoke_authentication(self) -> bool:
        """認証を取り消し
        
        Returns:
            bool: 取り消し成功の場合True
        """
        try:
            # トークンを削除
            success = self.token_manager.clear_tokens()
            
            # クライアント情報も削除
            self.storage.delete_client_data(self.server_url, self.user_id)
            
            # 内部状態をクリア
            self._client_info = None
            self.pkce_handler.clear()
            
            logger.info("Authentication revoked")
            return success
            
        except Exception as e:
            logger.error(f"Failed to revoke authentication: {e}")
            return False
    
    async def _ensure_server_metadata(self):
        """サーバーメタデータの確保"""
        if self._server_metadata is None:
            self._server_metadata = await self.discovery.discover_server_metadata(self.server_url)
            logger.debug("Server metadata obtained")
    
    async def _ensure_client_registered(self):
        """クライアント登録の確保"""
        if self._client_info is None:
            # 保存されたクライアント情報を読み込み
            self._client_info = self.storage.load_client_data(self.server_url, self.user_id)
            
            if self._client_info is None:
                # 動的クライアント登録を実行
                self._client_info = await self._register_dynamic_client()
                
                # クライアント情報を保存
                if self._client_info:
                    self.storage.save_client_data(self.server_url, self._client_info, self.user_id)
    
    async def _register_dynamic_client(self) -> Dict[str, Any]:
        """動的クライアント登録 (RFC 7591)
        
        Returns:
            Dict[str, Any]: クライアント情報
            
        Raises:
            ClientRegistrationError: 登録に失敗した場合
        """
        await self._ensure_http_client()
        await self._ensure_server_metadata()
        
        registration_endpoint = self._server_metadata.get('registration_endpoint')
        if not registration_endpoint:
            raise ClientRegistrationError("Server does not support dynamic client registration")
        
        # サーバー設定を取得
        server_config = self.config.get_server_config(self.server_url)
        if not server_config:
            server_config = ServerConfig(url=self.server_url)
        
        # 登録データを構築
        registration_data = {
            'client_name': server_config.client_name,
            'redirect_uris': [server_config.redirect_uri or self.config.default_redirect_uri],
            'grant_types': server_config.grant_types,
            'response_types': server_config.response_types,
            'token_endpoint_auth_method': server_config.token_endpoint_auth_method,
            'scope': ' '.join(server_config.scopes)
        }
        
        try:
            response = await self._http_client.post(
                registration_endpoint,
                json=registration_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 201:
                client_info = response.json()
                logger.info(f"Dynamic client registration successful: {client_info.get('client_id')}")
                return client_info
            else:
                error_msg = f"Registration failed: HTTP {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise ClientRegistrationError(error_msg)
                
        except httpx.RequestError as e:
            logger.error(f"Network error during client registration: {e}")
            raise ClientRegistrationError(f"Registration request failed: {e}")
    
    async def _build_authorization_url(self, code_challenge: str, state: str) -> str:
        """認証URLを構築
        
        Args:
            code_challenge: PKCEチャレンジ
            state: stateパラメータ
            
        Returns:
            str: 認証URL
        """
        await self._ensure_server_metadata()
        await self._ensure_client_registered()
        
        authorization_endpoint = self._server_metadata['authorization_endpoint']
        client_id = self._client_info['client_id']
        
        # サーバー設定を取得
        server_config = self.config.get_server_config(self.server_url)
        if not server_config:
            server_config = ServerConfig(url=self.server_url)
        
        # 認証パラメータを構築
        auth_params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': server_config.redirect_uri or self.config.default_redirect_uri,
            'scope': ' '.join(server_config.scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        return f"{authorization_endpoint}?{urlencode(auth_params)}"
    
    async def _exchange_authorization_code(self, authorization_code: str) -> Dict[str, Any]:
        """Authorization codeをaccess tokenに交換
        
        Args:
            authorization_code: 認証コード
            
        Returns:
            Dict[str, Any]: トークンデータ
            
        Raises:
            OAuth2Error: トークン交換に失敗した場合
        """
        await self._ensure_http_client()
        await self._ensure_server_metadata()
        await self._ensure_client_registered()
        
        token_endpoint = self._server_metadata['token_endpoint']
        client_id = self._client_info['client_id']
        code_verifier = self.pkce_handler.get_code_verifier()
        
        # サーバー設定を取得
        server_config = self.config.get_server_config(self.server_url)
        if not server_config:
            server_config = ServerConfig(url=self.server_url)
        
        # トークンリクエストデータを構築
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': server_config.redirect_uri or self.config.default_redirect_uri,
            'client_id': client_id,
            'code_verifier': code_verifier
        }
        
        try:
            response = await self._http_client.post(
                token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                logger.info("Access token obtained successfully")
                return token_response
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error_description', f"HTTP {response.status_code}")
                logger.error(f"Token exchange failed: {error_msg}")
                raise OAuth2Error(
                    f"Token exchange failed: {error_msg}",
                    oauth_error=error_data.get('error'),
                    error_description=error_data.get('error_description')
                )
                
        except httpx.RequestError as e:
            logger.error(f"Network error during token exchange: {e}")
            raise NetworkError(f"Token exchange request failed: {e}")
    
    async def _refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """リフレッシュトークンを使用してアクセストークンを更新
        
        Args:
            refresh_token: リフレッシュトークン
            
        Returns:
            Dict[str, Any]: 新しいトークンデータ
            
        Raises:
            OAuth2Error: トークン更新に失敗した場合
        """
        await self._ensure_http_client()
        await self._ensure_server_metadata()
        await self._ensure_client_registered()
        
        token_endpoint = self._server_metadata['token_endpoint']
        client_id = self._client_info['client_id']
        
        # リフレッシュリクエストデータを構築
        refresh_data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': client_id
        }
        
        try:
            response = await self._http_client.post(
                token_endpoint,
                data=refresh_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                logger.info("Access token refreshed successfully")
                return token_response
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error_description', f"HTTP {response.status_code}")
                logger.error(f"Token refresh failed: {error_msg}")
                raise OAuth2Error(
                    f"Token refresh failed: {error_msg}",
                    oauth_error=error_data.get('error'),
                    error_description=error_data.get('error_description')
                )
                
        except httpx.RequestError as e:
            logger.error(f"Network error during token refresh: {e}")
            raise NetworkError(f"Token refresh request failed: {e}")