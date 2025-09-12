"""
CryptoUtils ユニットテスト
暗号化ユーティリティのテストケース
"""

import pytest
import json
from agents.mcp_client.utils.crypto import CryptoUtils


class TestCryptoUtils:
    """CryptoUtilsのテストクラス"""
    
    @pytest.fixture
    def crypto_utils(self):
        """CryptoUtilsインスタンスを作成"""
        return CryptoUtils("test_password")
    
    @pytest.fixture
    def sample_data(self):
        """テスト用データ"""
        return {
            'access_token': 'sample_access_token',
            'refresh_token': 'sample_refresh_token',
            'expires_in': 3600,
            'token_type': 'Bearer'
        }
    
    def test_encrypt_decrypt_data(self, crypto_utils, sample_data):
        """データ暗号化・復号化のテスト"""
        # 暗号化
        encrypted_data = crypto_utils.encrypt_data(sample_data)
        
        assert isinstance(encrypted_data, str)
        assert len(encrypted_data) > 0
        
        # 復号化
        decrypted_data = crypto_utils.decrypt_data(encrypted_data)
        
        assert decrypted_data == sample_data
    
    def test_encrypt_decrypt_token(self, crypto_utils, sample_data):
        """トークン暗号化・復号化のテスト"""
        # トークン暗号化
        encrypted_token = crypto_utils.encrypt_token(sample_data)
        
        assert isinstance(encrypted_token, str)
        assert len(encrypted_token) > 0
        
        # トークン復号化
        decrypted_token = crypto_utils.decrypt_token(encrypted_token)
        
        assert decrypted_token == sample_data
    
    def test_encrypt_empty_data(self, crypto_utils):
        """空データの暗号化テスト"""
        empty_data = {}
        
        encrypted = crypto_utils.encrypt_data(empty_data)
        decrypted = crypto_utils.decrypt_data(encrypted)
        
        assert decrypted == empty_data
    
    def test_encrypt_complex_data(self, crypto_utils):
        """複雑なデータの暗号化テスト"""
        complex_data = {
            'string': 'test_string',
            'number': 12345,
            'boolean': True,
            'null': None,
            'list': [1, 2, 3, 'four'],
            'nested': {
                'inner_key': 'inner_value',
                'inner_list': ['a', 'b', 'c']
            }
        }
        
        encrypted = crypto_utils.encrypt_data(complex_data)
        decrypted = crypto_utils.decrypt_data(encrypted)
        
        assert decrypted == complex_data
    
    def test_encrypt_unicode_data(self, crypto_utils):
        """Unicode文字の暗号化テスト"""
        unicode_data = {
            'japanese': 'こんにちは',
            'emoji': '🔐🛡️',
            'chinese': '你好',
            'arabic': 'مرحبا'
        }
        
        encrypted = crypto_utils.encrypt_data(unicode_data)
        decrypted = crypto_utils.decrypt_data(encrypted)
        
        assert decrypted == unicode_data
    
    def test_different_passwords_different_results(self):
        """異なるパスワードで異なる結果を生成することのテスト"""
        data = {'test': 'data'}
        
        crypto1 = CryptoUtils("password1")
        crypto2 = CryptoUtils("password2")
        
        encrypted1 = crypto1.encrypt_data(data)
        encrypted2 = crypto2.encrypt_data(data)
        
        # 異なるパスワードでは異なる暗号化結果
        assert encrypted1 != encrypted2
    
    def test_same_data_different_results(self, crypto_utils, sample_data):
        """同じデータでも暗号化する度に異なる結果を生成することのテスト"""
        encrypted1 = crypto_utils.encrypt_data(sample_data)
        encrypted2 = crypto_utils.encrypt_data(sample_data)
        
        # 同じデータでもソルトにより異なる暗号化結果
        assert encrypted1 != encrypted2
        
        # しかし復号化すると同じデータになる
        decrypted1 = crypto_utils.decrypt_data(encrypted1)
        decrypted2 = crypto_utils.decrypt_data(encrypted2)
        
        assert decrypted1 == sample_data
        assert decrypted2 == sample_data
    
    def test_decrypt_invalid_data(self, crypto_utils):
        """無効なデータの復号化エラーテスト"""
        with pytest.raises(ValueError):
            crypto_utils.decrypt_data("invalid_encrypted_data")
    
    def test_decrypt_wrong_password(self, sample_data):
        """間違ったパスワードでの復号化エラーテスト"""
        crypto1 = CryptoUtils("correct_password")
        crypto2 = CryptoUtils("wrong_password")
        
        encrypted = crypto1.encrypt_data(sample_data)
        
        with pytest.raises(ValueError):
            crypto2.decrypt_data(encrypted)
    
    def test_generate_random_key(self, crypto_utils):
        """ランダムキー生成のテスト"""
        # デフォルトの長さ（32バイト）
        key1 = crypto_utils.generate_random_key()
        key2 = crypto_utils.generate_random_key()
        
        assert isinstance(key1, str)
        assert isinstance(key2, str)
        assert key1 != key2  # 異なるキーが生成される
        
        # カスタムの長さ
        key_16 = crypto_utils.generate_random_key(16)
        key_64 = crypto_utils.generate_random_key(64)
        
        # Base64エンコードされた長さが期待値と一致するかチェック
        import base64
        decoded_16 = base64.b64decode(key_16.encode('ascii'))
        decoded_64 = base64.b64decode(key_64.encode('ascii'))
        
        assert len(decoded_16) == 16
        assert len(decoded_64) == 64
    
    def test_is_encrypted_data(self, crypto_utils, sample_data):
        """暗号化データ判定のテスト"""
        # 暗号化されたデータ
        encrypted = crypto_utils.encrypt_data(sample_data)
        assert CryptoUtils.is_encrypted_data(encrypted) is True
        
        # 暗号化されていないデータ
        plain_text = "plain_text_data"
        assert CryptoUtils.is_encrypted_data(plain_text) is False
        
        # JSON文字列
        json_string = json.dumps(sample_data)
        assert CryptoUtils.is_encrypted_data(json_string) is False
        
        # 空文字列
        assert CryptoUtils.is_encrypted_data("") is False
    
    def test_token_metadata(self, crypto_utils, sample_data):
        """トークン暗号化時のメタデータ追加テスト"""
        encrypted_token = crypto_utils.encrypt_token(sample_data)
        decrypted_full = crypto_utils.decrypt_data(encrypted_token)
        
        # メタデータが追加されていることを確認
        assert 'token_data' in decrypted_full
        assert 'encrypted_at' in decrypted_full
        assert 'version' in decrypted_full
        
        # 元のトークンデータが正しく復号化されることを確認
        decrypted_token = crypto_utils.decrypt_token(encrypted_token)
        assert decrypted_token == sample_data
    
    def test_large_data_encryption(self, crypto_utils):
        """大きなデータの暗号化テスト"""
        # 大きなデータを生成
        large_data = {
            'large_text': 'x' * 10000,  # 10KB のテキスト
            'large_list': list(range(1000)),
            'nested_data': {
                str(i): f'value_{i}' for i in range(100)
            }
        }
        
        encrypted = crypto_utils.encrypt_data(large_data)
        decrypted = crypto_utils.decrypt_data(encrypted)
        
        assert decrypted == large_data
    
    def test_encryption_consistency(self, crypto_utils, sample_data):
        """暗号化の一貫性テスト"""
        # 複数回暗号化・復号化しても一貫した結果が得られることを確認
        for _ in range(10):
            encrypted = crypto_utils.encrypt_data(sample_data)
            decrypted = crypto_utils.decrypt_data(encrypted)
            assert decrypted == sample_data
    
    def test_default_password_warning(self, caplog):
        """デフォルトパスワード使用時の警告テスト"""
        import os
        
        # 環境変数をクリア（デフォルトパスワードを使用させる）
        if 'MCP_CRYPTO_PASSWORD' in os.environ:
            old_password = os.environ.pop('MCP_CRYPTO_PASSWORD')
        else:
            old_password = None
        
        try:
            # デフォルトパスワードでCryptoUtilsを作成
            crypto_utils = CryptoUtils()
            
            # 警告ログが出力されることを確認
            assert "Using default password" in caplog.text
            
        finally:
            # 環境変数を復元
            if old_password is not None:
                os.environ['MCP_CRYPTO_PASSWORD'] = old_password


if __name__ == '__main__':
    pytest.main([__file__])