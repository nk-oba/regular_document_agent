"""
セッションベースのGoogle認証管理システム
ブラウザセッション単位で認証情報を管理
"""
import os
import json
import uuid
import time
import logging
from typing import Optional, Dict
from fastapi import Request, Response
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class SessionAuthManager:
    """セッションベースの認証管理"""
    
    def __init__(self):
        self.sessions_file = "auth_sessions.json"
        self.session_timeout = 24 * 60 * 60  # 24時間
        self._sessions: Dict[str, dict] = {}
        self._load_sessions()
    
    def _load_sessions(self):
        """セッション情報を読み込み"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r') as f:
                    data = json.load(f)
                    # 期限切れセッションを除去
                    current_time = time.time()
                    self._sessions = {
                        sid: session_data 
                        for sid, session_data in data.items()
                        if session_data.get('expires_at', 0) > current_time
                    }
                    # 変更があった場合は保存
                    if len(self._sessions) != len(data):
                        self._save_sessions()
            except Exception as e:
                logger.warning(f"Failed to load sessions: {e}")
                self._sessions = {}
    
    def _save_sessions(self):
        """セッション情報を保存"""
        try:
            with open(self.sessions_file, 'w') as f:
                json.dump(self._sessions, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions: {e}")
    
    def create_session(self, user_info: dict, credentials: Credentials) -> str:
        """新しいセッションを作成"""
        session_id = str(uuid.uuid4())
        expires_at = time.time() + self.session_timeout
        
        self._sessions[session_id] = {
            'user_info': user_info,
            'credentials': credentials.to_json(),
            'created_at': time.time(),
            'expires_at': expires_at,
            'last_accessed': time.time()
        }
        
        self._save_sessions()
        logger.info(f"Created new session: {session_id} for user: {user_info.get('email')}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """セッション情報を取得"""
        if not session_id or session_id not in self._sessions:
            return None
        
        session_data = self._sessions[session_id]
        
        # 期限チェック
        if session_data.get('expires_at', 0) <= time.time():
            self.delete_session(session_id)
            return None
        
        # 最終アクセス時刻を更新
        session_data['last_accessed'] = time.time()
        self._save_sessions()
        
        return session_data
    
    def delete_session(self, session_id: str):
        """セッションを削除"""
        if session_id in self._sessions:
            user_email = self._sessions[session_id].get('user_info', {}).get('email', 'unknown')
            del self._sessions[session_id]
            self._save_sessions()
            logger.info(f"Deleted session: {session_id} for user: {user_email}")
    
    def get_session_id_from_request(self, request: Request) -> Optional[str]:
        """リクエストからセッションIDを取得"""
        return request.cookies.get('auth_session_id')
    
    def set_session_cookie(self, response: Response, session_id: str):
        """レスポンスにセッションクッキーを設定"""
        response.set_cookie(
            key='auth_session_id',
            value=session_id,
            max_age=self.session_timeout,
            httponly=True,
            secure=False,  # 開発環境ではFalse
            samesite='lax'
        )
    
    def clear_session_cookie(self, response: Response):
        """セッションクッキーを削除"""
        response.delete_cookie('auth_session_id')
    
    def get_user_info(self, request: Request) -> Optional[dict]:
        """リクエストからユーザー情報を取得"""
        session_id = self.get_session_id_from_request(request)
        if not session_id:
            return None
        
        session_data = self.get_session(session_id)
        if not session_data:
            return None
        
        return session_data.get('user_info')
    
    def get_credentials(self, request: Request) -> Optional[Credentials]:
        """リクエストから認証情報を取得"""
        session_id = self.get_session_id_from_request(request)
        if not session_id:
            return None
        
        session_data = self.get_session(session_id)
        if not session_data:
            return None
        
        try:
            credentials_json = session_data.get('credentials')
            if credentials_json:
                return Credentials.from_authorized_user_info(json.loads(credentials_json))
        except Exception as e:
            logger.error(f"Failed to load credentials from session: {e}")
        
        return None
    
    def is_authenticated(self, request: Request) -> bool:
        """リクエストが認証済みかチェック"""
        user_info = self.get_user_info(request)
        return user_info is not None
    
    def cleanup_expired_sessions(self):
        """期限切れセッションをクリーンアップ"""
        current_time = time.time()
        expired_sessions = [
            sid for sid, session_data in self._sessions.items()
            if session_data.get('expires_at', 0) <= current_time
        ]
        
        for sid in expired_sessions:
            self.delete_session(sid)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

# グローバルインスタンス
_session_auth_manager = None

def get_session_auth_manager() -> SessionAuthManager:
    """セッション認証マネージャーのシングルトンインスタンスを取得"""
    global _session_auth_manager
    if _session_auth_manager is None:
        _session_auth_manager = SessionAuthManager()
    return _session_auth_manager
