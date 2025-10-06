"""
セッションベースのGoogle認証管理システム
ブラウザセッション単位で認証情報を管理
"""
import os
import json
import uuid
import time
import logging
import fcntl
import tempfile
import shutil
from typing import Optional, Dict
from fastapi import Request, Response
from google.oauth2.credentials import Credentials
from pathlib import Path

logger = logging.getLogger(__name__)

class SessionAuthManager:
    """セッションベースの認証管理（改善版）"""
    
    def __init__(self):
        # 現在のディレクトリから相対パスを使用
        self.sessions_dir = Path("auth_storage/sessions/auth_sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.session_timeout = 24 * 60 * 60  # 24時間
        self._sessions: Dict[str, dict] = {}
        self._load_all_sessions()
    
    def _get_session_file_path(self, session_id: str) -> Path:
        """セッションファイルのパスを取得"""
        return self.sessions_dir / f"{session_id}.json"
    
    def _load_all_sessions(self):
        """全セッション情報を読み込み"""
        try:
            current_time = time.time()
            loaded_sessions = {}
            
            # セッションディレクトリ内の全ファイルを読み込み
            for session_file in self.sessions_dir.glob("*.json"):
                try:
                    with open(session_file, 'r') as f:
                        # ファイルロックを取得
                        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                        try:
                            session_data = json.load(f)
                            session_id = session_file.stem
                            
                            # 期限切れチェック
                            if session_data.get('expires_at', 0) > current_time:
                                loaded_sessions[session_id] = session_data
                            else:
                                # 期限切れセッションを削除
                                self._delete_session_file(session_file)
                        finally:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception as e:
                    logger.warning(f"Failed to load session file {session_file}: {e}")
                    # 破損ファイルを削除
                    self._delete_session_file(session_file)
            
            self._sessions = loaded_sessions
            
            # 期限切れセッションの数をログ出力
            if len(loaded_sessions) != len(list(self.sessions_dir.glob("*.json"))):
                logger.info(f"Cleaned up expired sessions")
                
        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
            self._sessions = {}
    
    def _save_session_file(self, session_id: str, session_data: dict):
        """セッションファイルを安全に保存"""
        session_file = self._get_session_file_path(session_id)
        
        try:
            # 一時ファイルに書き込み
            temp_file = session_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                # ファイルロックを取得
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(session_data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # ディスクに確実に書き込み
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # アトミックな移動
            shutil.move(str(temp_file), str(session_file))
            logger.debug(f"Session saved: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            # 一時ファイルを削除
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def _delete_session_file(self, session_file: Path):
        """セッションファイルを削除"""
        try:
            session_file.unlink()
            logger.debug(f"Session file deleted: {session_file}")
        except Exception as e:
            logger.warning(f"Failed to delete session file {session_file}: {e}")
    
    def _save_session_to_database(self, session_id: str, session_data: dict):
        """セッション情報をデータベースに保存"""
        try:
            # データベース初期化を保証
            from .database_init import ensure_auth_database_initialized
            if not ensure_auth_database_initialized():
                logger.warning("Failed to initialize auth database, skipping database save")
                return
            
            import sqlite3
            db_path = "auth_storage/auth_sessions.db"
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            user_info = session_data.get('user_info', {})
            email = user_info.get('email', '')
            
            # ログインセッションを保存
            cursor.execute("""
                INSERT OR REPLACE INTO login_sessions 
                (id, email, user_info, created_at, expires_at, last_accessed, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                email,
                json.dumps(user_info),
                session_data.get('created_at'),
                session_data.get('expires_at'),
                session_data.get('last_accessed'),
                'active'
            ))
            
            # ADKユーザーIDを生成して関連付け
            if email:
                import hashlib
                normalized_email = email.strip().lower()
                adk_user_id = hashlib.sha256(normalized_email.encode('utf-8')).hexdigest()[:16]
                
                cursor.execute("""
                    INSERT OR REPLACE INTO adk_sessions 
                    (login_session_id, adk_user_id, created_at)
                    VALUES (?, ?, ?)
                """, (session_id, adk_user_id, session_data.get('created_at')))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Session saved to database: {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session to database: {e}")
            # データベースエラーは致命的ではないので続行
    
    def create_session(self, user_info: dict, credentials: Credentials) -> str:
        """新しいセッションを作成"""
        session_id = str(uuid.uuid4())
        expires_at = time.time() + self.session_timeout

        session_data = {
            'user_info': user_info,
            'google_user_id': user_info.get('id'),  # Google User IDを明示的に保存
            'credentials': credentials.to_json(),
            'created_at': time.time(),
            'expires_at': expires_at,
            'last_accessed': time.time()
        }
        
        # セッションファイルに保存
        self._save_session_file(session_id, session_data)
        
        # データベースにも保存
        self._save_session_to_database(session_id, session_data)
        
        # メモリにも保存
        self._sessions[session_id] = session_data
        
        logger.info(f"Created new session: {session_id} for user: {user_info.get('email')}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """セッション情報を取得"""
        if not session_id:
            return None
        
        # まずメモリから確認
        if session_id in self._sessions:
            session_data = self._sessions[session_id]
            if session_data.get('expires_at', 0) > time.time():
                # 最終アクセス時刻を更新
                session_data['last_accessed'] = time.time()
                self._save_session_file(session_id, session_data)
                return session_data
            else:
                # 期限切れセッションを削除
                self.delete_session(session_id)
                return None
        
        # メモリにない場合はファイルから読み込み
        session_file = self._get_session_file_path(session_id)
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        session_data = json.load(f)
                        if session_data.get('expires_at', 0) > time.time():
                            # メモリに追加
                            self._sessions[session_id] = session_data
                            # 最終アクセス時刻を更新
                            session_data['last_accessed'] = time.time()
                            self._save_session_file(session_id, session_data)
                            return session_data
                        else:
                            # 期限切れセッションを削除
                            self.delete_session(session_id)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                self.delete_session(session_id)
        
        return None
    
    def delete_session(self, session_id: str):
        """セッションを削除"""
        if session_id in self._sessions:
            user_email = self._sessions[session_id].get('user_info', {}).get('email', 'unknown')
            del self._sessions[session_id]
            logger.info(f"Deleted session from memory: {session_id} for user: {user_email}")
        
        # ファイルも削除
        session_file = self._get_session_file_path(session_id)
        if session_file.exists():
            self._delete_session_file(session_file)
    
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

    def get_google_user_id(self, request: Request) -> Optional[str]:
        """リクエストからGoogle User IDを取得"""
        session_id = self.get_session_id_from_request(request)
        if not session_id:
            return None

        session_data = self.get_session(session_id)
        if not session_data:
            return None

        return session_data.get('google_user_id')
    
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
        expired_sessions = []
        
        # メモリ内の期限切れセッションをチェック
        for sid, session_data in self._sessions.items():
            if session_data.get('expires_at', 0) <= current_time:
                expired_sessions.append(sid)
        
        # 期限切れセッションを削除
        for sid in expired_sessions:
            self.delete_session(sid)
        
        # ファイルシステムの期限切れセッションもチェック
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        session_data = json.load(f)
                        if session_data.get('expires_at', 0) <= current_time:
                            self._delete_session_file(session_file)
                            # メモリからも削除
                            session_id = session_file.stem
                            if session_id in self._sessions:
                                del self._sessions[session_id]
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                logger.warning(f"Failed to check session file {session_file}: {e}")
                # 破損ファイルを削除
                self._delete_session_file(session_file)
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    def get_session_stats(self) -> dict:
        """セッション統計情報を取得"""
        current_time = time.time()
        total_sessions = len(self._sessions)
        active_sessions = sum(
            1 for session_data in self._sessions.values()
            if session_data.get('expires_at', 0) > current_time
        )
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "expired_sessions": total_sessions - active_sessions
        }

# グローバルインスタンス
_session_auth_manager = None

def get_session_auth_manager() -> SessionAuthManager:
    """セッション認証マネージャーのシングルトンインスタンスを取得"""
    global _session_auth_manager
    if _session_auth_manager is None:
        _session_auth_manager = SessionAuthManager()
    return _session_auth_manager
