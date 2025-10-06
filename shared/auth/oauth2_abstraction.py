"""
汎用OAuth2認証システム
Google以外のOAuth2プロバイダーに対応
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests


class OAuth2Credentials:
    """汎用OAuth2認証情報クラス"""
    
    def __init__(self, access_token: str, refresh_token: str, 
                 token_uri: str, client_id: str, client_secret: str,
                 expires_in: Optional[int] = None):
        """
        Args:
            access_token: アクセストークン
            refresh_token: リフレッシュトークン
            token_uri: トークンエンドポイントのURI
            client_id: クライアントID
            client_secret: クライアントシークレット
            expires_in: トークンの有効期限（秒）
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self._expires_at = None
        
        if expires_in:
            self._expires_at = datetime.now() + timedelta(seconds=expires_in)
    
    def get_access_token(self) -> Optional[str]:
        """アクセストークンを取得"""
        return self.access_token
    
    def refresh_token(self) -> bool:
        """リフレッシュトークンを使用してアクセストークンを更新"""
        try:
            response = requests.post(self.token_uri, data={
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            })
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data['access_token']
                
                # 有効期限を更新
                if 'expires_in' in data:
                    self._expires_at = datetime.now() + timedelta(seconds=data['expires_in'])
                
                # リフレッシュトークンが更新された場合は保存
                if 'refresh_token' in data:
                    self.refresh_token = data['refresh_token']
                
                logging.info("Successfully refreshed OAuth2 token")
                return True
            else:
                logging.error(f"Failed to refresh token: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Exception during token refresh: {e}")
            return False
    
    def is_valid(self) -> bool:
        """認証情報が有効かどうかを確認"""
        if not self.access_token:
            return False
        
        # 有効期限が設定されている場合はチェック
        if self._expires_at:
            return datetime.now() < self._expires_at
        
        # 有効期限が不明な場合は、トークンが存在するかどうかのみチェック
        return True
    
    def get_auth_headers(self) -> Dict[str, str]:
        """認証ヘッダーを取得"""
        return {
            'Authorization': f'Bearer {self.get_access_token()}'
        }


# 便利な関数
def create_oauth2_credentials(access_token: str, refresh_token: str, 
                            token_uri: str, client_id: str, client_secret: str,
                            expires_in: Optional[int] = None) -> OAuth2Credentials:
    """
    OAuth2認証情報を作成する便利関数
    
    Args:
        access_token: アクセストークン
        refresh_token: リフレッシュトークン
        token_uri: トークンエンドポイントのURI
        client_id: クライアントID
        client_secret: クライアントシークレット
        expires_in: トークンの有効期限（秒）
    
    Returns:
        OAuth2Credentials: OAuth2認証情報オブジェクト
    """
    return OAuth2Credentials(
        access_token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        expires_in=expires_in
    )
