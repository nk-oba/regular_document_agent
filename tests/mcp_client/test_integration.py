"""
統合テスト
MCP認証フレームワーク全体の統合テスト
"""

import pytest
import asyncio
import httpx
from unittest.mock import Mock, patch, AsyncMock
from agents.mcp_client.auth.client import MCPAuthClient
from agents.mcp_client.transport.http_client import AuthenticatedHTTPClient
from agents.mcp_client.integration import MCPClientFactory
from agents.mcp_client.config.settings import MCPClientConfig, ServerConfig


class TestMCPClientIntegration:
    """MCP認証クライアント統合テスト"""
    
    @pytest.fixture
    def server_url(self):
        """テスト用サーバーURL"""
        return "https://test-server.example.com"
    
    @pytest.fixture
    def mock_server_metadata(self):
        """モックサーバーメタデータ"""
        return {
            'authorization_endpoint': 'https://test-server.example.com/authorize',
            'token_endpoint': 'https://test-server.example.com/token',
            'registration_endpoint': 'https://test-server.example.com/register',
            'scopes_supported': ['read', 'write'],
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code', 'refresh_token'],
            'code_challenge_methods_supported': ['S256']
        }
    
    @pytest.fixture
    def mock_client_info(self):
        """モッククライアント情報"""
        return {
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'registration_client_uri': 'https://test-server.example.com/register/test_client_id'
        }
    
    @pytest.fixture
    def mock_token_data(self):
        """モックトークンデータ"""
        return {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'scope': 'read write'
        }
    
    @pytest.mark.asyncio
    async def test_complete_auth_flow(
        self, 
        server_url, 
        mock_server_metadata, 
        mock_client_info, 
        mock_token_data
    ):
        """完全な認証フロー統合テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # サーバー発見のモック
            metadata_response = Mock()
            metadata_response.status_code = 200
            metadata_response.json.return_value = mock_server_metadata
            
            # クライアント登録のモック
            registration_response = Mock()
            registration_response.status_code = 201
            registration_response.json.return_value = mock_client_info
            
            # トークン交換のモック
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = mock_token_data
            
            # HTTPレスポンスの設定
            mock_client.get = AsyncMock(return_value=metadata_response)
            mock_client.post = AsyncMock(side_effect=[registration_response, token_response])
            
            # MCPAuthClientでテスト
            auth_client = MCPAuthClient(server_url, "test_user")
            
            async with auth_client:
                # 認証フロー開始
                auth_url = await auth_client.start_authentication_flow()
                assert 'authorize' in auth_url
                assert 'client_id=' in auth_url
                assert 'code_challenge=' in auth_url
                assert 'state=' in auth_url
                
                # 認証完了
                success = await auth_client.complete_authentication_flow('test_auth_code', 'test_state')
                assert success is True
                
                # 認証後のトークン確認
                access_token = await auth_client.get_access_token()
                assert access_token == 'test_access_token'
    
    @pytest.mark.asyncio
    async def test_authenticated_http_request(
        self,
        server_url,
        mock_server_metadata,
        mock_client_info,
        mock_token_data
    ):
        """認証付きHTTPリクエスト統合テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # 既存トークンの設定（認証済み状態をシミュレート）
            with patch('agents.mcp_client.auth.token_manager.TokenManager.get_access_token') as mock_get_token:
                mock_get_token.return_value = 'valid_access_token'
                
                # APIレスポンスのモック
                api_response = Mock()
                api_response.status_code = 200
                api_response.json.return_value = {'data': 'test_data'}
                
                mock_client.request = AsyncMock(return_value=api_response)
                
                # 認証付きHTTPクライアントでテスト
                auth_client = MCPAuthClient(server_url, "test_user")
                http_client = AuthenticatedHTTPClient(auth_client)
                
                async with auth_client:
                    response = await http_client.get('/api/test')
                    
                    assert response.status_code == 200
                    
                    # 認証ヘッダーが含まれていることを確認
                    call_args = mock_client.request.call_args
                    headers = call_args[1]['headers']
                    assert 'Authorization' in headers
                    assert headers['Authorization'] == 'Bearer valid_access_token'
    
    @pytest.mark.asyncio
    async def test_http_401_handling(
        self,
        server_url,
        mock_server_metadata,
        mock_client_info,
        mock_token_data
    ):
        """HTTP 401レスポンス処理統合テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # 最初は401レスポンス
            unauthorized_response = Mock()
            unauthorized_response.status_code = 401
            
            mock_client.request = AsyncMock(return_value=unauthorized_response)
            
            auth_client = MCPAuthClient(server_url, "test_user")
            
            async with auth_client:
                # 401レスポンスで AuthenticationRequiredError が発生することを確認
                from agents.mcp_client.auth.exceptions import AuthenticationRequiredError
                
                with pytest.raises(AuthenticationRequiredError) as exc_info:
                    await auth_client.make_authenticated_request('GET', '/api/protected')
                
                # エラーに認証URLが含まれていることを確認
                assert hasattr(exc_info.value, 'auth_url')
    
    @pytest.mark.asyncio
    async def test_token_refresh_integration(
        self,
        server_url,
        mock_server_metadata,
        mock_client_info,
        mock_token_data
    ):
        """トークン更新統合テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # リフレッシュトークンレスポンスのモック
            refresh_response = Mock()
            refresh_response.status_code = 200
            new_token_data = mock_token_data.copy()
            new_token_data['access_token'] = 'refreshed_access_token'
            refresh_response.json.return_value = new_token_data
            
            mock_client.post = AsyncMock(return_value=refresh_response)
            
            auth_client = MCPAuthClient(server_url, "test_user")
            
            # リフレッシュトークンが存在する状態をモック
            with patch.object(auth_client.token_manager, 'get_refresh_token', return_value='valid_refresh_token'):
                with patch.object(auth_client.token_manager, 'get_access_token', return_value=None):
                    async with auth_client:
                        # トークン取得時にリフレッシュが実行される
                        access_token = await auth_client.get_access_token()
                        
                        # 新しいアクセストークンが取得されることを確認
                        assert access_token == 'refreshed_access_token'
    
    def test_factory_integration(self, server_url):
        """ファクトリー統合テスト"""
        
        # 認証クライアント作成
        auth_client = MCPClientFactory.create_auth_client(server_url, "test_user")
        assert auth_client.server_url == server_url
        assert auth_client.user_id == "test_user"
        
        # HTTPクライアント作成
        http_client = MCPClientFactory.create_http_client(server_url, "test_user")
        assert isinstance(http_client, AuthenticatedHTTPClient)
        assert http_client.auth_client.server_url == server_url
        
        # シンプルクライアント作成
        simple_client = MCPClientFactory.create_simple_client(server_url, "test_user")
        assert simple_client.auth_client.server_url == server_url
    
    def test_config_integration(self, server_url):
        """設定統合テスト"""
        
        # カスタム設定作成
        config = MCPClientConfig(
            timeout=60,
            max_retries=5,
            token_cache_ttl=600
        )
        
        # サーバー設定追加
        server_config = ServerConfig(
            url=server_url,
            name="Test Server",
            scopes=['read', 'write', 'admin'],
            redirect_uri='http://localhost:8080/callback'
        )
        config.add_server(server_config)
        
        # 設定を使用してクライアント作成
        auth_client = MCPAuthClient(server_url, "test_user", config)
        
        assert auth_client.config.timeout == 60
        assert auth_client.config.max_retries == 5
        assert auth_client.config.token_cache_ttl == 600
        
        # サーバー設定が正しく取得できることを確認
        retrieved_config = auth_client.config.get_server_config(server_url)
        assert retrieved_config.name == "Test Server"
        assert retrieved_config.scopes == ['read', 'write', 'admin']
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, server_url):
        """エラーハンドリング統合テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # ネットワークエラーのシミュレート
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Network error"))
            
            auth_client = MCPAuthClient(server_url, "test_user")
            
            async with auth_client:
                from agents.mcp_client.auth.exceptions import ServerDiscoveryError
                
                with pytest.raises(ServerDiscoveryError):
                    await auth_client._ensure_server_metadata()
    
    @pytest.mark.asyncio
    async def test_concurrent_authentication(self, server_url, mock_server_metadata, mock_client_info):
        """並行認証処理テスト"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_client.aclose = AsyncMock()
            
            # レスポンスのモック
            metadata_response = Mock()
            metadata_response.status_code = 200
            metadata_response.json.return_value = mock_server_metadata
            
            registration_response = Mock()
            registration_response.status_code = 201
            registration_response.json.return_value = mock_client_info
            
            mock_client.get = AsyncMock(return_value=metadata_response)
            mock_client.post = AsyncMock(return_value=registration_response)
            
            # 複数のクライアントで並行処理
            clients = [
                MCPAuthClient(server_url, f"user_{i}")
                for i in range(3)
            ]
            
            async def start_auth_flow(client):
                async with client:
                    return await client.start_authentication_flow()
            
            # 並行実行
            auth_urls = await asyncio.gather(*[
                start_auth_flow(client) for client in clients
            ])
            
            # 全て成功することを確認
            assert len(auth_urls) == 3
            for auth_url in auth_urls:
                assert 'authorize' in auth_url
    
    def test_legacy_integration_migration(self, server_url, tmp_path):
        """レガシーシステム統合・移行テスト"""
        from agents.mcp_client.integration import LegacyIntegration
        
        # 既存の認証情報ファイルを作成
        old_credentials = {
            'access_token': 'old_access_token',
            'refresh_token': 'old_refresh_token',
            'token_type': 'Bearer',
            'expires_in': 3600
        }
        
        old_file = tmp_path / "old_credentials.json"
        import json
        old_file.write_text(json.dumps(old_credentials))
        
        # 移行実行
        with patch('agents.mcp_client.utils.storage.SecureStorage') as mock_storage_class:
            mock_storage = Mock()
            mock_storage_class.return_value = mock_storage
            
            with patch('agents.mcp_client.auth.token_manager.TokenManager') as mock_token_manager_class:
                mock_token_manager = Mock()
                mock_token_manager.store_tokens.return_value = True
                mock_token_manager_class.return_value = mock_token_manager
                
                success = LegacyIntegration.migrate_existing_tokens(
                    str(old_file),
                    server_url,
                    "test_user"
                )
                
                assert success is True
                
                # トークンが保存されたことを確認
                mock_token_manager.store_tokens.assert_called_once()
                stored_data = mock_token_manager.store_tokens.call_args[0][0]
                assert stored_data['access_token'] == 'old_access_token'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])