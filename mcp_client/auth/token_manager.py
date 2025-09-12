"""
トークンマネージャー
OAuth 2.1トークンのライフサイクル管理
"""

import time
from typing import Dict, Any, Optional, Tuple
from ..utils.storage import SecureStorage
import logging

logger = logging.getLogger(__name__)


class TokenManager:
    """OAuth 2.1トークンライフサイクル管理クラス
    
    アクセストークンとリフレッシュトークンの管理、
    自動更新、有効期限チェックを提供
    """
    
    def __init__(self, server_url: str, user_id: Optional[str] = None, storage: Optional[SecureStorage] = None):
        """トークンマネージャーを初期化
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID（マルチユーザー対応）
            storage: セキュアストレージインスタンス
        """
        self.server_url = server_url
        self.user_id = user_id
        self.storage = storage or SecureStorage()
        
        # メモリ内キャッシュ
        self._token_cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5分間のキャッシュ
        
        logger.debug(f"TokenManager initialized for {server_url} (user: {user_id})")
    
    def store_tokens(self, token_data: Dict[str, Any]) -> bool:
        """トークンデータを保存
        
        Args:
            token_data: OAuth 2.1トークンレスポンス
                - access_token: アクセストークン
                - refresh_token: リフレッシュトークン（オプション）
                - expires_in: 有効期限（秒）
                - token_type: トークンタイプ（通常は'Bearer'）
                - scope: スコープ
        
        Returns:
            bool: 保存成功の場合True
        """
        try:
            # expires_atを計算
            enhanced_token_data = token_data.copy()
            if 'expires_in' in token_data:
                enhanced_token_data['expires_at'] = time.time() + token_data['expires_in']
            
            # 保存時刻を記録
            enhanced_token_data['stored_at'] = time.time()
            
            # 永続化
            success = self.storage.save_token_data(
                self.server_url, 
                enhanced_token_data, 
                self.user_id
            )
            
            if success:
                # メモリキャッシュを更新
                self._token_cache = enhanced_token_data
                self._cache_timestamp = time.time()
                logger.info("Tokens stored successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to store tokens: {e}")
            return False
    
    def get_access_token(self) -> Optional[str]:
        """有効なアクセストークンを取得
        
        Returns:
            Optional[str]: 有効なアクセストークン、存在しない場合はNone
        """
        token_data = self._get_cached_tokens()
        
        if not token_data:
            logger.debug("No token data available")
            return None
        
        access_token = token_data.get('access_token')
        if not access_token:
            logger.debug("No access token in stored data")
            return None
        
        # トークンの有効性をチェック
        if self._is_token_expired(token_data):
            logger.debug("Access token is expired")
            return None
        
        return access_token
    
    def get_refresh_token(self) -> Optional[str]:
        """リフレッシュトークンを取得
        
        Returns:
            Optional[str]: リフレッシュトークン、存在しない場合はNone
        """
        token_data = self._get_cached_tokens()
        
        if not token_data:
            return None
        
        return token_data.get('refresh_token')
    
    def is_token_valid(self) -> bool:
        """トークンが有効かチェック
        
        Returns:
            bool: 有効なアクセストークンが存在する場合True
        """
        return self.get_access_token() is not None
    
    def is_token_expired(self) -> bool:
        """トークンが期限切れかチェック
        
        Returns:
            bool: トークンが期限切れの場合True
        """
        token_data = self._get_cached_tokens()
        
        if not token_data:
            return True
        
        return self._is_token_expired(token_data)
    
    def get_token_info(self) -> Optional[Dict[str, Any]]:
        """トークン情報を取得（デバッグ用）
        
        Returns:
            Optional[Dict[str, Any]]: トークン情報（access_tokenは除外）
        """
        token_data = self._get_cached_tokens()
        
        if not token_data:
            return None
        
        # セキュリティのためaccess_tokenを除外
        info = token_data.copy()
        if 'access_token' in info:
            info['access_token'] = '***REDACTED***'
        if 'refresh_token' in info:
            info['refresh_token'] = '***REDACTED***'
        
        return info
    
    def clear_tokens(self) -> bool:
        """保存されているトークンを削除
        
        Returns:
            bool: 削除成功の場合True
        """
        try:
            success = self.storage.delete_token_data(self.server_url, self.user_id)
            
            if success:
                # メモリキャッシュもクリア
                self._token_cache = None
                self._cache_timestamp = None
                logger.info("Tokens cleared successfully")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to clear tokens: {e}")
            return False
    
    def get_authorization_header(self) -> Optional[Dict[str, str]]:
        """Authorization headerを取得
        
        Returns:
            Optional[Dict[str, str]]: Authorizationヘッダー
        """
        access_token = self.get_access_token()
        
        if not access_token:
            return None
        
        return {'Authorization': f'Bearer {access_token}'}
    
    def _get_cached_tokens(self) -> Optional[Dict[str, Any]]:
        """キャッシュされたトークンを取得
        
        Returns:
            Optional[Dict[str, Any]]: トークンデータ
        """
        current_time = time.time()
        
        # キャッシュが有効かチェック
        if (self._token_cache is not None and 
            self._cache_timestamp is not None and
            current_time - self._cache_timestamp < self._cache_ttl):
            return self._token_cache
        
        # ストレージから読み込み
        token_data = self.storage.load_token_data(self.server_url, self.user_id)
        
        if token_data:
            # キャッシュを更新
            self._token_cache = token_data
            self._cache_timestamp = current_time
        
        return token_data
    
    def _is_token_expired(self, token_data: Dict[str, Any]) -> bool:
        """トークンの期限切れチェック
        
        Args:
            token_data: トークンデータ
            
        Returns:
            bool: 期限切れの場合True
        """
        expires_at = token_data.get('expires_at')
        
        if not expires_at:
            # expires_atが設定されていない場合は有効とみなす
            return False
        
        # 余裕を持って30秒前に期限切れとみなす
        return time.time() >= (expires_at - 30)
    
    def _invalidate_cache(self) -> None:
        """キャッシュを無効化"""
        self._token_cache = None
        self._cache_timestamp = None
    
    def refresh_cache(self) -> None:
        """キャッシュを強制更新"""
        self._invalidate_cache()
        self._get_cached_tokens()
    
    def get_expires_in(self) -> Optional[int]:
        """トークンの残り有効時間（秒）を取得
        
        Returns:
            Optional[int]: 残り有効時間、計算不可能な場合はNone
        """
        token_data = self._get_cached_tokens()
        
        if not token_data:
            return None
        
        expires_at = token_data.get('expires_at')
        if not expires_at:
            return None
        
        remaining = int(expires_at - time.time())
        return max(0, remaining)
    
    def will_expire_soon(self, threshold_seconds: int = 300) -> bool:
        """トークンがまもなく期限切れになるかチェック
        
        Args:
            threshold_seconds: 閾値（秒）。デフォルトは5分
            
        Returns:
            bool: まもなく期限切れになる場合True
        """
        expires_in = self.get_expires_in()
        
        if expires_in is None:
            return False
        
        return expires_in <= threshold_seconds