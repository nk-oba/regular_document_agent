"""
PKCE (Proof Key for Code Exchange) Handler
RFC 7636準拠のPKCE実装
"""

import secrets
import hashlib
import base64
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class PKCEHandler:
    """PKCE (Proof Key for Code Exchange) 実装クラス
    
    OAuth 2.1でmandatoryとされているPKCEの実装を提供
    RFC 7636に完全準拠
    """
    
    def __init__(self):
        """PKCEハンドラーを初期化"""
        self._code_verifier: Optional[str] = None
        self._code_challenge: Optional[str] = None
        self._state: Optional[str] = None
    
    def generate_pkce_params(self) -> Tuple[str, str, str]:
        """PKCE認証用パラメータを生成
        
        Returns:
            Tuple[str, str, str]: (code_verifier, code_challenge, state)
            
        Raises:
            ValueError: パラメータ生成に失敗した場合
        """
        try:
            # RFC 7636: code_verifierは43-128文字のランダム文字列
            self._code_verifier = base64.urlsafe_b64encode(
                secrets.token_bytes(32)
            ).decode('utf-8').rstrip('=')
            
            # RFC 7636: code_challengeはcode_verifierのSHA256ハッシュをBase64URLエンコード
            challenge_bytes = hashlib.sha256(
                self._code_verifier.encode('utf-8')
            ).digest()
            self._code_challenge = base64.urlsafe_b64encode(
                challenge_bytes
            ).decode('utf-8').rstrip('=')
            
            # OAuth 2.1: stateパラメータは必須
            self._state = secrets.token_urlsafe(32)
            
            logger.debug("PKCE parameters generated successfully")
            logger.debug(f"Code verifier length: {len(self._code_verifier)}")
            logger.debug(f"Code challenge length: {len(self._code_challenge)}")
            logger.debug(f"State length: {len(self._state)}")
            
            return self._code_verifier, self._code_challenge, self._state
            
        except Exception as e:
            logger.error(f"Failed to generate PKCE parameters: {e}")
            raise ValueError(f"PKCE parameter generation failed: {e}")
    
    def validate_state(self, received_state: str) -> bool:
        """受信したstateパラメータを検証
        
        Args:
            received_state: 認証サーバーから返されたstateパラメータ
            
        Returns:
            bool: 検証結果
        """
        if not self._state:
            logger.error("No state parameter stored for validation")
            return False
        
        is_valid = secrets.compare_digest(self._state, received_state)
        
        if is_valid:
            logger.debug("State parameter validation successful")
        else:
            logger.warning("State parameter validation failed")
            logger.warning(f"Expected: {self._state[:10]}...")
            logger.warning(f"Received: {received_state[:10]}...")
        
        return is_valid
    
    def get_code_verifier(self) -> Optional[str]:
        """保存されているcode_verifierを取得
        
        Returns:
            Optional[str]: code_verifier、生成されていない場合はNone
        """
        return self._code_verifier
    
    def get_code_challenge(self) -> Optional[str]:
        """保存されているcode_challengeを取得
        
        Returns:
            Optional[str]: code_challenge、生成されていない場合はNone
        """
        return self._code_challenge
    
    def get_state(self) -> Optional[str]:
        """保存されているstateパラメータを取得
        
        Returns:
            Optional[str]: stateパラメータ、生成されていない場合はNone
        """
        return self._state
    
    def clear(self) -> None:
        """保存されているPKCEパラメータをクリア"""
        self._code_verifier = None
        self._code_challenge = None
        self._state = None
        logger.debug("PKCE parameters cleared")
    
    @staticmethod
    def verify_code_challenge_method() -> str:
        """使用するcode_challenge_methodを返す
        
        Returns:
            str: 常に'S256' (SHA256ハッシュ)
        """
        return 'S256'
    
    def is_ready(self) -> bool:
        """PKCEパラメータが生成済みかチェック
        
        Returns:
            bool: 全てのパラメータが生成されている場合True
        """
        return all([
            self._code_verifier,
            self._code_challenge, 
            self._state
        ])
    
    def __str__(self) -> str:
        """デバッグ用文字列表現"""
        return (
            f"PKCEHandler("
            f"verifier={'***' if self._code_verifier else None}, "
            f"challenge={self._code_challenge[:10] + '...' if self._code_challenge else None}, "
            f"state={self._state[:10] + '...' if self._state else None})"
        )