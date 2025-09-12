"""
サーバー発見 (Server Discovery)
OAuth 2.1 Authorization Server Metadata Discovery (RFC 8414)
"""

import json
from typing import Dict, Any, Optional, List
from urllib.parse import urljoin
import httpx
import logging
from .exceptions import ServerDiscoveryError, NetworkError

logger = logging.getLogger(__name__)


class ServerDiscovery:
    """OAuth 2.1 Authorization Server Metadata Discovery
    
    RFC 8414に従ってサーバーのメタデータを発見・取得
    """
    
    def __init__(self, timeout: int = 30, verify_ssl: bool = True):
        """サーバー発見を初期化
        
        Args:
            timeout: HTTPリクエストのタイムアウト（秒）
            verify_ssl: SSL証明書の検証を行うか
        """
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}
        
    async def discover_server_metadata(self, server_url: str, force_refresh: bool = False) -> Dict[str, Any]:
        """サーバーメタデータを発見・取得
        
        Args:
            server_url: MCPサーバーのベースURL
            force_refresh: キャッシュを無視して強制更新
            
        Returns:
            Dict[str, Any]: サーバーメタデータ
            
        Raises:
            ServerDiscoveryError: メタデータ取得に失敗した場合
        """
        # キャッシュチェック
        if not force_refresh and server_url in self._metadata_cache:
            logger.debug(f"Using cached metadata for {server_url}")
            return self._metadata_cache[server_url]
        
        try:
            # Well-knownエンドポイントのURL生成
            well_known_url = self._build_well_known_url(server_url)
            
            logger.info(f"Discovering server metadata from: {well_known_url}")
            
            # HTTPSクライアント作成
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.verify_ssl
            ) as client:
                
                # メタデータ取得
                response = await client.get(well_known_url)
                
                if response.status_code == 200:
                    metadata = response.json()
                    
                    # メタデータの検証
                    validated_metadata = self._validate_metadata(metadata, server_url)
                    
                    # キャッシュに保存
                    self._metadata_cache[server_url] = validated_metadata
                    
                    logger.info(f"Successfully discovered metadata for {server_url}")
                    logger.debug(f"Available endpoints: {list(validated_metadata.keys())}")
                    
                    return validated_metadata
                
                elif response.status_code == 404:
                    # Well-knownエンドポイントが存在しない場合、デフォルト値を生成
                    logger.warning(f"Well-known endpoint not found for {server_url}, using defaults")
                    return self._generate_default_metadata(server_url)
                
                else:
                    raise ServerDiscoveryError(
                        f"Failed to fetch metadata: HTTP {response.status_code} - {response.text}"
                    )
                    
        except httpx.RequestError as e:
            logger.error(f"Network error during discovery: {e}")
            raise NetworkError(f"Failed to connect to {well_known_url}: {e}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in metadata response: {e}")
            raise ServerDiscoveryError(f"Invalid metadata format: {e}")
        
        except Exception as e:
            logger.error(f"Unexpected error during discovery: {e}")
            raise ServerDiscoveryError(f"Server discovery failed: {e}")
    
    def _build_well_known_url(self, server_url: str) -> str:
        """Well-knownエンドポイントのURLを構築
        
        Args:
            server_url: サーバーのベースURL
            
        Returns:
            str: Well-knownエンドポイントのURL
        """
        # RFC 8414: OAuth 2.0 Authorization Server Metadata
        return urljoin(server_url.rstrip('/'), '/.well-known/oauth-protected-resource')
    
    def _validate_metadata(self, metadata: Dict[str, Any], server_url: str) -> Dict[str, Any]:
        """メタデータの妥当性を検証
        
        Args:
            metadata: サーバーから取得したメタデータ
            server_url: サーバーURL
            
        Returns:
            Dict[str, Any]: 検証済みメタデータ
            
        Raises:
            ServerDiscoveryError: メタデータが無効な場合
        """
        try:
            # 必須フィールドの確認
            required_fields = ['authorization_endpoint', 'token_endpoint']
            missing_fields = []
            
            for field in required_fields:
                if field not in metadata:
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"Missing required fields: {missing_fields}, generating defaults")
                # デフォルト値で補完
                metadata.update(self._generate_default_endpoints(server_url))
            
            # エンドポイントURLの正規化
            base_url = server_url.rstrip('/')
            for endpoint_field in ['authorization_endpoint', 'token_endpoint', 'registration_endpoint']:
                if endpoint_field in metadata:
                    endpoint_url = metadata[endpoint_field]
                    if not endpoint_url.startswith('http'):
                        # 相対URLを絶対URLに変換
                        metadata[endpoint_field] = urljoin(base_url, endpoint_url)
            
            # サポートされる機能の確認
            self._validate_oauth_features(metadata)
            
            return metadata
            
        except Exception as e:
            raise ServerDiscoveryError(f"Metadata validation failed: {e}")
    
    def _validate_oauth_features(self, metadata: Dict[str, Any]):
        """OAuth 2.1機能のサポート状況を確認
        
        Args:
            metadata: メタデータ
        """
        # PKCE サポートの確認
        code_challenge_methods = metadata.get('code_challenge_methods_supported', [])
        if 'S256' not in code_challenge_methods:
            logger.warning("Server may not support PKCE S256 method")
            # デフォルトで S256 を追加
            metadata.setdefault('code_challenge_methods_supported', ['S256'])
        
        # Grant typesの確認
        grant_types = metadata.get('grant_types_supported', [])
        required_grants = ['authorization_code', 'refresh_token']
        for grant_type in required_grants:
            if grant_type not in grant_types:
                logger.warning(f"Server may not support {grant_type} grant type")
        
        # Response typesの確認
        response_types = metadata.get('response_types_supported', [])
        if 'code' not in response_types:
            logger.warning("Server may not support 'code' response type")
    
    def _generate_default_metadata(self, server_url: str) -> Dict[str, Any]:
        """デフォルトのメタデータを生成
        
        Args:
            server_url: サーバーURL
            
        Returns:
            Dict[str, Any]: デフォルトメタデータ
        """
        base_url = server_url.rstrip('/')
        
        default_metadata = {
            'issuer': base_url,
            **self._generate_default_endpoints(base_url),
            'scopes_supported': ['read', 'write'],
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': ['none', 'client_secret_basic'],
        }
        
        # キャッシュに保存
        self._metadata_cache[server_url] = default_metadata
        
        logger.info(f"Generated default metadata for {server_url}")
        return default_metadata
    
    def _generate_default_endpoints(self, server_url: str) -> Dict[str, str]:
        """デフォルトのエンドポイントを生成
        
        Args:
            server_url: サーバーURL
            
        Returns:
            Dict[str, str]: エンドポイント辞書
        """
        base_url = server_url.rstrip('/')
        
        return {
            'authorization_endpoint': f'{base_url}/authorize',
            'token_endpoint': f'{base_url}/token',
            'registration_endpoint': f'{base_url}/register',
        }
    
    def get_cached_metadata(self, server_url: str) -> Optional[Dict[str, Any]]:
        """キャッシュされたメタデータを取得
        
        Args:
            server_url: サーバーURL
            
        Returns:
            Optional[Dict[str, Any]]: メタデータ、存在しない場合はNone
        """
        return self._metadata_cache.get(server_url)
    
    def clear_cache(self, server_url: Optional[str] = None):
        """メタデータキャッシュをクリア
        
        Args:
            server_url: 特定のサーバーのみクリアする場合のURL。Noneの場合は全てクリア
        """
        if server_url:
            self._metadata_cache.pop(server_url, None)
            logger.debug(f"Cleared metadata cache for {server_url}")
        else:
            self._metadata_cache.clear()
            logger.debug("Cleared all metadata cache")
    
    def extract_endpoints(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """メタデータからエンドポイントを抽出
        
        Args:
            metadata: サーバーメタデータ
            
        Returns:
            Dict[str, str]: エンドポイント情報
        """
        endpoints = {}
        
        endpoint_fields = [
            'authorization_endpoint',
            'token_endpoint', 
            'registration_endpoint',
            'revocation_endpoint',
            'introspection_endpoint'
        ]
        
        for field in endpoint_fields:
            if field in metadata:
                endpoints[field] = metadata[field]
        
        return endpoints
    
    def get_supported_features(self, metadata: Dict[str, Any]) -> Dict[str, List[str]]:
        """サーバーがサポートする機能を取得
        
        Args:
            metadata: サーバーメタデータ
            
        Returns:
            Dict[str, List[str]]: サポートされる機能のリスト
        """
        features = {}
        
        feature_fields = [
            'scopes_supported',
            'response_types_supported',
            'grant_types_supported',
            'code_challenge_methods_supported',
            'token_endpoint_auth_methods_supported'
        ]
        
        for field in feature_fields:
            if field in metadata:
                features[field] = metadata[field]
        
        return features