"""
既存システム統合モジュール
既存のMCP ADA認証システムと新しい認証フレームワークの統合
"""

import logging
from typing import Optional, Dict, Any
from .auth.client import MCPAuthClient
from .transport.http_client import AuthenticatedHTTPClient, SimpleAuthenticatedClient
from .config.settings import MCPClientConfig, ServerConfig

logger = logging.getLogger(__name__)


class MCPClientFactory:
    """MCP認証クライアントファクトリー
    
    既存システムとの統合を簡単にするためのファクトリークラス
    """
    
    @staticmethod
    def create_auth_client(
        server_url: str,
        user_id: Optional[str] = None,
        config: Optional[MCPClientConfig] = None
    ) -> MCPAuthClient:
        """認証クライアントを作成
        
        Args:
            server_url: MCPサーバーURL
            user_id: ユーザーID
            config: クライアント設定
            
        Returns:
            MCPAuthClient: 認証クライアント
        """
        logger.info(f"Creating MCP auth client for {server_url}")
        return MCPAuthClient(server_url, user_id, config)
    
    @staticmethod
    def create_http_client(
        server_url: str,
        user_id: Optional[str] = None,
        auth_callback: Optional[callable] = None,
        config: Optional[MCPClientConfig] = None
    ) -> AuthenticatedHTTPClient:
        """認証付きHTTPクライアントを作成
        
        Args:
            server_url: MCPサーバーURL
            user_id: ユーザーID
            auth_callback: 認証コールバック
            config: クライアント設定
            
        Returns:
            AuthenticatedHTTPClient: 認証付きHTTPクライアント
        """
        auth_client = MCPClientFactory.create_auth_client(server_url, user_id, config)
        http_client = AuthenticatedHTTPClient(auth_client)
        
        if auth_callback:
            http_client.set_auth_callback(auth_callback)
        
        logger.info(f"Created HTTP client for {server_url}")
        return http_client
    
    @staticmethod
    def create_simple_client(
        server_url: str,
        user_id: Optional[str] = None,
        auth_callback: Optional[callable] = None
    ) -> SimpleAuthenticatedClient:
        """シンプル認証クライアントを作成
        
        Args:
            server_url: MCPサーバーURL
            user_id: ユーザーID
            auth_callback: 認証コールバック
            
        Returns:
            SimpleAuthenticatedClient: シンプル認証クライアント
        """
        logger.info(f"Creating simple client for {server_url}")
        return SimpleAuthenticatedClient(server_url, user_id, auth_callback)


class LegacyIntegration:
    """既存システム統合サポート
    
    既存のMCP ADA認証システムとの互換性を提供
    """
    
    @staticmethod
    def migrate_existing_tokens(
        old_credentials_file: str,
        server_url: str,
        user_id: Optional[str] = None
    ) -> bool:
        """既存のトークンを新システムに移行
        
        Args:
            old_credentials_file: 既存の認証情報ファイルパス
            server_url: MCPサーバーURL
            user_id: ユーザーID
            
        Returns:
            bool: 移行成功の場合True
        """
        try:
            import json
            import os
            from .utils.storage import SecureStorage
            from .auth.token_manager import TokenManager
            
            if not os.path.exists(old_credentials_file):
                logger.warning(f"Old credentials file not found: {old_credentials_file}")
                return False
            
            # 既存の認証情報を読み込み
            with open(old_credentials_file, 'r') as f:
                old_credentials = json.load(f)
            
            # 新しいストレージシステムに移行
            storage = SecureStorage()
            token_manager = TokenManager(server_url, user_id, storage)
            
            # トークンデータを変換
            token_data = {
                'access_token': old_credentials.get('access_token'),
                'refresh_token': old_credentials.get('refresh_token'),
                'token_type': old_credentials.get('token_type', 'Bearer'),
                'expires_in': old_credentials.get('expires_in'),
                'expires_at': old_credentials.get('expires_at'),
                'scope': old_credentials.get('scope')
            }
            
            # 新システムに保存
            success = token_manager.store_tokens(token_data)
            
            if success:
                logger.info(f"Successfully migrated tokens for {server_url}")
                # 既存ファイルをバックアップ
                backup_file = f"{old_credentials_file}.backup"
                os.rename(old_credentials_file, backup_file)
                logger.info(f"Old credentials backed up to: {backup_file}")
            
            return success
            
        except Exception as e:
            logger.error(f"Token migration failed: {e}")
            return False
    
    @staticmethod
    def create_server_config_from_existing(
        server_url: str,
        existing_config: Dict[str, Any]
    ) -> ServerConfig:
        """既存設定から新しいServerConfigを作成
        
        Args:
            server_url: サーバーURL
            existing_config: 既存設定辞書
            
        Returns:
            ServerConfig: 新しいサーバー設定
        """
        return ServerConfig(
            url=server_url,
            name=existing_config.get('name'),
            authorization_endpoint=existing_config.get('authorization_endpoint'),
            token_endpoint=existing_config.get('token_endpoint'),
            registration_endpoint=existing_config.get('registration_endpoint'),
            scopes=existing_config.get('scopes', ['read', 'write']),
            redirect_uri=existing_config.get('redirect_uri'),
            client_name=existing_config.get('client_name', 'MCP ADA Client')
        )


class WebIntegration:
    """Webアプリケーション統合サポート
    
    FastAPI、Flask等のWebフレームワークとの統合機能
    """
    
    @staticmethod
    def create_fastapi_auth_dependency(
        server_url: str,
        config: Optional[MCPClientConfig] = None
    ):
        """FastAPI用の認証依存関数を作成
        
        Args:
            server_url: MCPサーバーURL
            config: クライアント設定
            
        Returns:
            callable: FastAPI依存関数
        """
        try:
            from fastapi import Depends, HTTPException, status
            from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
            
            security = HTTPBearer()
            
            async def authenticate_request(
                credentials: HTTPAuthorizationCredentials = Depends(security)
            ) -> str:
                """リクエスト認証"""
                # 実装例：トークンの検証
                # 実際の実装では、トークンの有効性をチェック
                return credentials.credentials
            
            return authenticate_request
            
        except ImportError:
            logger.warning("FastAPI not available for integration")
            return None
    
    @staticmethod
    def create_flask_auth_decorator(
        server_url: str,
        config: Optional[MCPClientConfig] = None
    ):
        """Flask用の認証デコレータを作成
        
        Args:
            server_url: MCPサーバーURL
            config: クライアント設定
            
        Returns:
            callable: Flask認証デコレータ
        """
        try:
            from functools import wraps
            from flask import request, jsonify
            
            def require_auth(f):
                @wraps(f)
                def decorated_function(*args, **kwargs):
                    auth_header = request.headers.get('Authorization')
                    if not auth_header or not auth_header.startswith('Bearer '):
                        return jsonify({'error': 'Authentication required'}), 401
                    
                    # トークン検証ロジック
                    token = auth_header[7:]  # "Bearer " を除去
                    # 実際の実装では、トークンの有効性をチェック
                    
                    return f(*args, **kwargs)
                return decorated_function
            
            return require_auth
            
        except ImportError:
            logger.warning("Flask not available for integration")
            return None


class CLIIntegration:
    """CLI統合サポート
    
    コマンドラインツールとの統合機能
    """
    
    @staticmethod
    def create_click_auth_command(server_url: str):
        """Click用の認証コマンドを作成
        
        Args:
            server_url: MCPサーバーURL
            
        Returns:
            callable: Click認証コマンド
        """
        try:
            import click
            import asyncio
            
            @click.command()
            @click.option('--user-id', help='User ID for authentication')
            def authenticate(user_id: Optional[str] = None):
                """Authenticate with MCP server"""
                async def auth_flow():
                    async with MCPAuthClient(server_url, user_id) as client:
                        auth_url = await client.start_authentication_flow()
                        
                        click.echo(f"Please visit the following URL to authenticate:")
                        click.echo(f"{auth_url}")
                        
                        auth_code = click.prompt("Enter the authorization code")
                        state = click.prompt("Enter the state parameter", default="")
                        
                        success = await client.complete_authentication_flow(auth_code, state)
                        
                        if success:
                            click.echo("Authentication successful!")
                        else:
                            click.echo("Authentication failed!", err=True)
                
                asyncio.run(auth_flow())
            
            return authenticate
            
        except ImportError:
            logger.warning("Click not available for CLI integration")
            return None
    
    @staticmethod
    def create_argparse_auth_subcommand(parser, server_url: str):
        """argparse用の認証サブコマンドを追加
        
        Args:
            parser: argparseパーサー
            server_url: MCPサーバーURL
        """
        auth_parser = parser.add_subparser('auth', help='Authentication commands')
        auth_parser.add_argument('--user-id', help='User ID for authentication')
        auth_parser.add_argument('--server-url', default=server_url, help='MCP server URL')
        
        def handle_auth_command(args):
            """認証コマンドハンドラー"""
            import asyncio
            
            async def auth_flow():
                async with MCPAuthClient(args.server_url, args.user_id) as client:
                    auth_url = await client.start_authentication_flow()
                    
                    print(f"Please visit the following URL to authenticate:")
                    print(f"{auth_url}")
                    
                    auth_code = input("Enter the authorization code: ")
                    state = input("Enter the state parameter (optional): ")
                    
                    success = await client.complete_authentication_flow(auth_code, state)
                    
                    if success:
                        print("Authentication successful!")
                    else:
                        print("Authentication failed!")
            
            asyncio.run(auth_flow())
        
        auth_parser.set_defaults(func=handle_auth_command)


def get_integration_examples() -> Dict[str, str]:
    """統合例のコードを取得
    
    Returns:
        Dict[str, str]: 統合例のコード辞書
    """
    examples = {
        'basic_usage': '''
# 基本的な使用方法
async with MCPAuthClient("https://mcp-server.example.com") as client:
    response = await client.make_authenticated_request("GET", "/api/data")
    print(response.json())
''',
        
        'with_callback': '''
# 認証コールバック付き
def handle_auth(auth_url: str):
    print(f"Please authenticate at: {auth_url}")
    # ブラウザを開くなどの処理

client = SimpleAuthenticatedClient(
    "https://mcp-server.example.com",
    auth_callback=handle_auth
)

async with client:
    response = await client.get("/api/resources")
''',
        
        'factory_usage': '''
# ファクトリーを使用した作成
from agents.mcp_client.integration import MCPClientFactory

# HTTPクライアントを作成
http_client = MCPClientFactory.create_http_client(
    "https://mcp-server.example.com",
    user_id="user123"
)

# リクエスト実行
async with http_client.auth_client:
    response = await http_client.get("/api/data")
''',
        
        'migration': '''
# 既存トークンの移行
from agents.mcp_client.integration import LegacyIntegration

success = LegacyIntegration.migrate_existing_tokens(
    old_credentials_file="/path/to/old_credentials.json",
    server_url="https://mcp-server.example.com",
    user_id="user123"
)

if success:
    print("Token migration successful!")
'''
    }
    
    return examples