"""
設定管理システム
MCP ADA準拠の設定とコンフィギュレーション管理
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """MCPサーバー固有の設定"""
    
    # 基本設定
    url: str
    name: Optional[str] = None
    
    # OAuth 2.1設定
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    registration_endpoint: Optional[str] = None
    
    # 動的発見設定
    well_known_endpoint: Optional[str] = None
    auto_discover: bool = True
    
    # 認証設定
    scopes: List[str] = field(default_factory=lambda: ['read', 'write'])
    redirect_uri: Optional[str] = None
    
    # クライアント設定
    client_name: str = "MCP ADA Client"
    grant_types: List[str] = field(default_factory=lambda: ['authorization_code', 'refresh_token'])
    response_types: List[str] = field(default_factory=lambda: ['code'])
    
    # セキュリティ設定
    require_pkce: bool = True
    token_endpoint_auth_method: str = 'none'  # PKCE使用のため
    
    def __post_init__(self):
        """設定の後処理と検証"""
        if self.name is None:
            self.name = self._extract_name_from_url()
        
        if self.well_known_endpoint is None and self.auto_discover:
            self.well_known_endpoint = self._generate_well_known_endpoint()
    
    def _extract_name_from_url(self) -> str:
        """URLからサーバー名を抽出"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            return parsed.netloc or self.url
        except Exception:
            return self.url
    
    def _generate_well_known_endpoint(self) -> str:
        """Well-knownエンドポイントのURLを生成"""
        base_url = self.url.rstrip('/')
        return f"{base_url}/.well-known/oauth-protected-resource"


@dataclass 
class MCPClientConfig:
    """MCP認証クライアントの設定"""
    
    # ストレージ設定
    storage_base_path: Optional[str] = None
    crypto_password: Optional[str] = None
    
    # HTTP設定
    timeout: int = 30
    max_retries: int = 3
    retry_backoff_factor: float = 1.0
    
    # キャッシュ設定
    token_cache_ttl: int = 300  # 5分
    metadata_cache_ttl: int = 3600  # 1時間
    
    # ログ設定
    log_level: str = 'INFO'
    log_auth_events: bool = True
    
    # セキュリティ設定
    require_https: bool = True
    validate_ssl: bool = True
    
    # デフォルトサーバー設定
    default_redirect_uri: str = 'http://localhost:8080/auth/callback'
    default_scopes: List[str] = field(default_factory=lambda: ['read', 'write'])
    
    # サーバー固有設定
    servers: Dict[str, ServerConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        """設定の後処理と初期化"""
        self._load_from_environment()
        self._validate_config()
    
    def _load_from_environment(self):
        """環境変数から設定を読み込み"""
        # ストレージ設定
        if not self.storage_base_path:
            self.storage_base_path = os.getenv(
                'MCP_CLIENT_STORAGE_PATH', 
                str(Path.home() / '.mcp_client')
            )
        
        if not self.crypto_password:
            self.crypto_password = os.getenv('MCP_CLIENT_CRYPTO_PASSWORD')
        
        # HTTP設定
        if timeout_env := os.getenv('MCP_CLIENT_TIMEOUT'):
            try:
                self.timeout = int(timeout_env)
            except ValueError:
                logger.warning(f"Invalid MCP_CLIENT_TIMEOUT value: {timeout_env}")
        
        # ログ設定
        if log_level_env := os.getenv('MCP_CLIENT_LOG_LEVEL'):
            self.log_level = log_level_env.upper()
        
        # セキュリティ設定
        if require_https_env := os.getenv('MCP_CLIENT_REQUIRE_HTTPS'):
            self.require_https = require_https_env.lower() in ('true', '1', 'yes')
        
        if validate_ssl_env := os.getenv('MCP_CLIENT_VALIDATE_SSL'):
            self.validate_ssl = validate_ssl_env.lower() in ('true', '1', 'yes')
    
    def _validate_config(self):
        """設定の妥当性をチェック"""
        # タイムアウト値のチェック
        if self.timeout <= 0:
            logger.warning("Invalid timeout value, using default 30 seconds")
            self.timeout = 30
        
        # リトライ回数のチェック
        if self.max_retries < 0:
            logger.warning("Invalid max_retries value, using default 3")
            self.max_retries = 3
        
        # ログレベルのチェック
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level not in valid_log_levels:
            logger.warning(f"Invalid log_level: {self.log_level}, using INFO")
            self.log_level = 'INFO'
    
    def add_server(self, server_config: ServerConfig):
        """サーバー設定を追加
        
        Args:
            server_config: サーバー設定
        """
        self.servers[server_config.url] = server_config
        logger.info(f"Added server config: {server_config.name} ({server_config.url})")
    
    def get_server_config(self, server_url: str) -> Optional[ServerConfig]:
        """サーバー設定を取得
        
        Args:
            server_url: サーバーのURL
            
        Returns:
            Optional[ServerConfig]: サーバー設定、存在しない場合はNone
        """
        return self.servers.get(server_url)
    
    def remove_server(self, server_url: str) -> bool:
        """サーバー設定を削除
        
        Args:
            server_url: サーバーのURL
            
        Returns:
            bool: 削除成功の場合True
        """
        if server_url in self.servers:
            del self.servers[server_url]
            logger.info(f"Removed server config: {server_url}")
            return True
        return False
    
    def list_servers(self) -> List[str]:
        """設定されているサーバーのリストを取得
        
        Returns:
            List[str]: サーバーURLのリスト
        """
        return list(self.servers.keys())
    
    def create_server_config(
        self,
        url: str,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        **kwargs
    ) -> ServerConfig:
        """サーバー設定を作成
        
        Args:
            url: サーバーURL
            name: サーバー名（オプション）
            scopes: スコープリスト（オプション）
            **kwargs: その他のServerConfig引数
            
        Returns:
            ServerConfig: 作成されたサーバー設定
        """
        # デフォルト値の設定
        if scopes is None:
            scopes = self.default_scopes.copy()
        
        if 'redirect_uri' not in kwargs:
            kwargs['redirect_uri'] = self.default_redirect_uri
        
        # ServerConfigの作成
        server_config = ServerConfig(
            url=url,
            name=name,
            scopes=scopes,
            **kwargs
        )
        
        # 自動的に追加
        self.add_server(server_config)
        
        return server_config
    
    def get_storage_path(self) -> Path:
        """ストレージベースパスを取得
        
        Returns:
            Path: ストレージパス
        """
        return Path(self.storage_base_path)
    
    def to_dict(self) -> Dict[str, Any]:
        """設定を辞書形式で取得
        
        Returns:
            Dict[str, Any]: 設定辞書
        """
        result = {
            'storage_base_path': self.storage_base_path,
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'retry_backoff_factor': self.retry_backoff_factor,
            'token_cache_ttl': self.token_cache_ttl,
            'metadata_cache_ttl': self.metadata_cache_ttl,
            'log_level': self.log_level,
            'log_auth_events': self.log_auth_events,
            'require_https': self.require_https,
            'validate_ssl': self.validate_ssl,
            'default_redirect_uri': self.default_redirect_uri,
            'default_scopes': self.default_scopes,
        }
        
        # パスワードは除外（セキュリティ上の理由）
        
        return result


# デフォルトのグローバル設定インスタンス
_default_config: Optional[MCPClientConfig] = None


def get_default_config() -> MCPClientConfig:
    """デフォルト設定を取得
    
    Returns:
        MCPClientConfig: デフォルト設定インスタンス
    """
    global _default_config
    
    if _default_config is None:
        _default_config = MCPClientConfig()
    
    return _default_config


def set_default_config(config: MCPClientConfig):
    """デフォルト設定を設定
    
    Args:
        config: 新しいデフォルト設定
    """
    global _default_config
    _default_config = config
    logger.info("Default config updated")