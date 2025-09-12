"""
TokenManager ユニットテスト
トークン管理機能のテストケース
"""

import pytest
import time
from unittest.mock import Mock, patch
from agents.mcp_client.auth.token_manager import TokenManager
from agents.mcp_client.utils.storage import SecureStorage


class TestTokenManager:
    """TokenManagerのテストクラス"""
    
    @pytest.fixture
    def mock_storage(self):
        """モックストレージを作成"""
        return Mock(spec=SecureStorage)
    
    @pytest.fixture
    def token_manager(self, mock_storage):
        """TokenManagerインスタンスを作成"""
        return TokenManager("https://example.com", "test_user", mock_storage)
    
    @pytest.fixture
    def sample_token_data(self):
        """サンプルトークンデータ"""
        return {
            'access_token': 'sample_access_token',
            'refresh_token': 'sample_refresh_token',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'scope': 'read write'
        }
    
    def test_store_tokens_success(self, token_manager, mock_storage, sample_token_data):
        """トークン保存成功のテスト"""
        mock_storage.save_token_data.return_value = True
        
        result = token_manager.store_tokens(sample_token_data)
        
        assert result is True
        mock_storage.save_token_data.assert_called_once()
        
        # expires_at が追加されていることを確認
        call_args = mock_storage.save_token_data.call_args[0]
        stored_data = call_args[1]
        assert 'expires_at' in stored_data
        assert 'stored_at' in stored_data
        assert stored_data['access_token'] == 'sample_access_token'
    
    def test_store_tokens_failure(self, token_manager, mock_storage, sample_token_data):
        """トークン保存失敗のテスト"""
        mock_storage.save_token_data.return_value = False
        
        result = token_manager.store_tokens(sample_token_data)
        
        assert result is False
    
    def test_get_access_token_valid(self, token_manager, mock_storage):
        """有効なアクセストークン取得のテスト"""
        valid_token_data = {
            'access_token': 'valid_token',
            'expires_at': time.time() + 3600  # 1時間後に期限切れ
        }
        mock_storage.load_token_data.return_value = valid_token_data
        
        token = token_manager.get_access_token()
        
        assert token == 'valid_token'
    
    def test_get_access_token_expired(self, token_manager, mock_storage):
        """期限切れアクセストークン取得のテスト"""
        expired_token_data = {
            'access_token': 'expired_token',
            'expires_at': time.time() - 3600  # 1時間前に期限切れ
        }
        mock_storage.load_token_data.return_value = expired_token_data
        
        token = token_manager.get_access_token()
        
        assert token is None
    
    def test_get_access_token_no_data(self, token_manager, mock_storage):
        """トークンデータなしの場合のテスト"""
        mock_storage.load_token_data.return_value = None
        
        token = token_manager.get_access_token()
        
        assert token is None
    
    def test_get_refresh_token(self, token_manager, mock_storage):
        """リフレッシュトークン取得のテスト"""
        token_data = {
            'refresh_token': 'sample_refresh_token'
        }
        mock_storage.load_token_data.return_value = token_data
        
        refresh_token = token_manager.get_refresh_token()
        
        assert refresh_token == 'sample_refresh_token'
    
    def test_is_token_valid_true(self, token_manager, mock_storage):
        """トークン有効性チェック（有効）のテスト"""
        valid_token_data = {
            'access_token': 'valid_token',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = valid_token_data
        
        assert token_manager.is_token_valid() is True
    
    def test_is_token_valid_false(self, token_manager, mock_storage):
        """トークン有効性チェック（無効）のテスト"""
        expired_token_data = {
            'access_token': 'expired_token',
            'expires_at': time.time() - 3600
        }
        mock_storage.load_token_data.return_value = expired_token_data
        
        assert token_manager.is_token_valid() is False
    
    def test_is_token_expired_true(self, token_manager, mock_storage):
        """トークン期限切れチェック（期限切れ）のテスト"""
        expired_token_data = {
            'access_token': 'expired_token',
            'expires_at': time.time() - 3600
        }
        mock_storage.load_token_data.return_value = expired_token_data
        
        assert token_manager.is_token_expired() is True
    
    def test_is_token_expired_false(self, token_manager, mock_storage):
        """トークン期限切れチェック（有効）のテスト"""
        valid_token_data = {
            'access_token': 'valid_token',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = valid_token_data
        
        assert token_manager.is_token_expired() is False
    
    def test_is_token_expired_no_expires_at(self, token_manager, mock_storage):
        """expires_at未設定時の期限切れチェックのテスト"""
        token_data = {
            'access_token': 'token_without_expiry'
        }
        mock_storage.load_token_data.return_value = token_data
        
        # expires_atが設定されていない場合は有効とみなす
        assert token_manager.is_token_expired() is False
    
    def test_clear_tokens(self, token_manager, mock_storage):
        """トークンクリアのテスト"""
        mock_storage.delete_token_data.return_value = True
        
        result = token_manager.clear_tokens()
        
        assert result is True
        mock_storage.delete_token_data.assert_called_once_with(
            "https://example.com", "test_user"
        )
    
    def test_get_authorization_header_valid(self, token_manager, mock_storage):
        """認証ヘッダー取得（有効トークン）のテスト"""
        valid_token_data = {
            'access_token': 'valid_token',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = valid_token_data
        
        header = token_manager.get_authorization_header()
        
        assert header == {'Authorization': 'Bearer valid_token'}
    
    def test_get_authorization_header_invalid(self, token_manager, mock_storage):
        """認証ヘッダー取得（無効トークン）のテスト"""
        mock_storage.load_token_data.return_value = None
        
        header = token_manager.get_authorization_header()
        
        assert header is None
    
    def test_get_token_info(self, token_manager, mock_storage):
        """トークン情報取得のテスト"""
        token_data = {
            'access_token': 'secret_token',
            'refresh_token': 'secret_refresh',
            'token_type': 'Bearer',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = token_data
        
        info = token_manager.get_token_info()
        
        # センシティブな情報がマスクされていることを確認
        assert info['access_token'] == '***REDACTED***'
        assert info['refresh_token'] == '***REDACTED***'
        assert info['token_type'] == 'Bearer'
        assert 'expires_at' in info
    
    def test_get_expires_in(self, token_manager, mock_storage):
        """残り有効時間取得のテスト"""
        expires_at = time.time() + 1800  # 30分後
        token_data = {
            'access_token': 'token',
            'expires_at': expires_at
        }
        mock_storage.load_token_data.return_value = token_data
        
        expires_in = token_manager.get_expires_in()
        
        # 誤差を考慮して範囲チェック
        assert 1790 <= expires_in <= 1800
    
    def test_get_expires_in_no_expiry(self, token_manager, mock_storage):
        """expires_at未設定時の残り有効時間取得のテスト"""
        token_data = {
            'access_token': 'token'
        }
        mock_storage.load_token_data.return_value = token_data
        
        expires_in = token_manager.get_expires_in()
        
        assert expires_in is None
    
    def test_will_expire_soon_true(self, token_manager, mock_storage):
        """まもなく期限切れチェック（期限切れ間近）のテスト"""
        expires_at = time.time() + 60  # 1分後
        token_data = {
            'access_token': 'token',
            'expires_at': expires_at
        }
        mock_storage.load_token_data.return_value = token_data
        
        # デフォルト閾値（5分）でテスト
        assert token_manager.will_expire_soon() is True
        
        # カスタム閾値（30秒）でテスト
        assert token_manager.will_expire_soon(30) is False
    
    def test_will_expire_soon_false(self, token_manager, mock_storage):
        """まもなく期限切れチェック（十分な時間）のテスト"""
        expires_at = time.time() + 3600  # 1時間後
        token_data = {
            'access_token': 'token',
            'expires_at': expires_at
        }
        mock_storage.load_token_data.return_value = token_data
        
        assert token_manager.will_expire_soon() is False
    
    def test_cache_functionality(self, token_manager, mock_storage):
        """キャッシュ機能のテスト"""
        token_data = {
            'access_token': 'cached_token',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = token_data
        
        # 1回目の呼び出し
        token1 = token_manager.get_access_token()
        
        # 2回目の呼び出し（キャッシュから取得）
        token2 = token_manager.get_access_token()
        
        assert token1 == token2
        # ストレージは1回だけ呼ばれる（キャッシュが効いている）
        assert mock_storage.load_token_data.call_count == 1
    
    def test_refresh_cache(self, token_manager, mock_storage):
        """キャッシュ更新のテスト"""
        token_data = {
            'access_token': 'token',
            'expires_at': time.time() + 3600
        }
        mock_storage.load_token_data.return_value = token_data
        
        # キャッシュに読み込み
        token_manager.get_access_token()
        assert mock_storage.load_token_data.call_count == 1
        
        # キャッシュを強制更新
        token_manager.refresh_cache()
        
        # 再度アクセス時にストレージから読み込み
        token_manager.get_access_token()
        assert mock_storage.load_token_data.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__])