"""
暗号化ユーティリティ
トークンの安全な暗号化/復号化機能を提供
"""

import os
import json
import base64
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import logging

logger = logging.getLogger(__name__)


class CryptoUtils:
    """暗号化ユーティリティクラス
    
    トークンや機密データの安全な暗号化/復号化を提供
    PBKDF2 + Fernetを使用した対称暗号化
    """
    
    def __init__(self, password: Optional[str] = None):
        """暗号化ユーティリティを初期化
        
        Args:
            password: 暗号化に使用するパスワード。Noneの場合は環境変数から取得
        """
        self._fernet: Optional[Fernet] = None
        self._salt: Optional[bytes] = None
        
        # パスワードの取得
        self._password = password or os.getenv('MCP_CRYPTO_PASSWORD', 'default_mcp_password')
        
        # 警告: デフォルトパスワードの使用
        if self._password == 'default_mcp_password':
            logger.warning("Using default password for encryption. Set MCP_CRYPTO_PASSWORD environment variable for production.")
    
    def _get_fernet(self) -> Fernet:
        """Fernetインスタンスを取得またはを生成
        
        Returns:
            Fernet: 暗号化/復号化インスタンス
        """
        if self._fernet is None:
            if self._salt is None:
                self._salt = os.urandom(16)  # 16バイトのソルト生成
            
            # PBKDF2でパスワードからキーを導出
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._salt,
                iterations=100000,  # OWASP推奨値
            )
            key = base64.urlsafe_b64encode(kdf.derive(self._password.encode()))
            self._fernet = Fernet(key)
        
        return self._fernet
    
    def encrypt_data(self, data: Dict[str, Any]) -> str:
        """データを暗号化
        
        Args:
            data: 暗号化するデータ（辞書形式）
            
        Returns:
            str: Base64エンコードされた暗号化データ
            
        Raises:
            ValueError: 暗号化に失敗した場合
        """
        try:
            # JSONシリアライゼーション
            json_data = json.dumps(data, ensure_ascii=False)
            
            # 暗号化
            fernet = self._get_fernet()
            encrypted_data = fernet.encrypt(json_data.encode('utf-8'))
            
            # ソルトと暗号化データを結合してBase64エンコード
            combined_data = self._salt + encrypted_data
            encoded_data = base64.b64encode(combined_data).decode('ascii')
            
            logger.debug(f"Successfully encrypted data (length: {len(encoded_data)})")
            return encoded_data
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt data: {e}")
    
    def decrypt_data(self, encrypted_data: str) -> Dict[str, Any]:
        """暗号化されたデータを復号化
        
        Args:
            encrypted_data: Base64エンコードされた暗号化データ
            
        Returns:
            Dict[str, Any]: 復号化されたデータ
            
        Raises:
            ValueError: 復号化に失敗した場合
        """
        try:
            # Base64デコード
            combined_data = base64.b64decode(encrypted_data.encode('ascii'))
            
            # ソルトと暗号化データを分離
            self._salt = combined_data[:16]  # 最初の16バイトがソルト
            encrypted_bytes = combined_data[16:]
            
            # 復号化
            fernet = self._get_fernet()
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            
            # JSONデシリアライゼーション
            json_data = decrypted_bytes.decode('utf-8')
            data = json.loads(json_data)
            
            logger.debug("Successfully decrypted data")
            return data
            
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")
    
    def encrypt_token(self, token_data: Dict[str, Any]) -> str:
        """トークンデータを暗号化
        
        Args:
            token_data: トークン情報（access_token, refresh_token等）
            
        Returns:
            str: 暗号化されたトークンデータ
        """
        # トークン固有の追加メタデータを付与
        enhanced_data = {
            'token_data': token_data,
            'encrypted_at': __import__('time').time(),
            'version': '1.0'
        }
        
        return self.encrypt_data(enhanced_data)
    
    def decrypt_token(self, encrypted_token: str) -> Dict[str, Any]:
        """暗号化されたトークンデータを復号化
        
        Args:
            encrypted_token: 暗号化されたトークンデータ
            
        Returns:
            Dict[str, Any]: トークン情報
        """
        decrypted_data = self.decrypt_data(encrypted_token)
        
        # バージョンチェック
        version = decrypted_data.get('version', '1.0')
        if version != '1.0':
            logger.warning(f"Token version mismatch: {version}")
        
        return decrypted_data.get('token_data', {})
    
    def generate_random_key(self, length: int = 32) -> str:
        """ランダムキーを生成
        
        Args:
            length: キーの長さ（バイト）
            
        Returns:
            str: Base64エンコードされたランダムキー
        """
        random_bytes = os.urandom(length)
        return base64.b64encode(random_bytes).decode('ascii')
    
    @staticmethod
    def is_encrypted_data(data: str) -> bool:
        """データが暗号化されているかチェック
        
        Args:
            data: チェック対象の文字列
            
        Returns:
            bool: 暗号化データの場合True
        """
        try:
            # Base64デコード可能かチェック
            decoded = base64.b64decode(data.encode('ascii'))
            # 最低限の長さチェック（ソルト16バイト + 暗号化データ）
            return len(decoded) > 16
        except Exception:
            return False