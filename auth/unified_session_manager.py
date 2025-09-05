"""
統合セッション管理システム
ログインセッションとADKセッションの二重管理を統合し、
単一のインターフェースで両方を効率的に管理
"""
import sqlite3
import logging
import hashlib
import time
import uuid
from typing import Optional, Dict, List, Tuple
from google.oauth2.credentials import Credentials
from fastapi import Request, Response

logger = logging.getLogger(__name__)

class UnifiedSessionManager:
    """統合セッション管理システム
    
    ログインセッション（ユーザー認証）とADKセッション（チャット管理）を
    単一のインターフェースで統合管理する
    """
    
    def __init__(self, adk_session_db_path: str = "sqlite:///./sessions.db"):
        self.adk_session_db_path = adk_session_db_path.replace('sqlite:///', '')
        self.session_timeout = 24 * 60 * 60  # 24時間
        
        # 既存のセッション管理システムとの互換性を保持
        from auth.session_auth import get_session_auth_manager
        from auth.session_sync_manager import get_session_sync_manager
        
        self.login_session_manager = get_session_auth_manager()
        self.sync_manager = get_session_sync_manager()
    
    def _get_stable_adk_user_id(self, email: str) -> str:
        """emailから安定したADKユーザーIDを生成"""
        if not email:
            return "anonymous"
        
        # 正規化して一貫性を保つ
        normalized_email = email.strip().lower()
        hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
        adk_user_id = hash_object.hexdigest()[:16]
        
        logger.debug(f"UnifiedSessionManager generated ADK user ID: {adk_user_id} for email: {normalized_email[:5]}...")
        
        return adk_user_id
    
    def create_unified_session(self, user_info: dict, credentials: Credentials) -> Dict:
        """統合セッションを作成
        
        Args:
            user_info: ユーザー情報（email, name等）
            credentials: OAuth認証情報
            
        Returns:
            統合セッション情報
        """
        try:
            email = user_info.get("email")
            if not email:
                raise ValueError("User email is required for unified session")
            
            # 1. ADK用の安定したユーザーIDを生成
            adk_user_id = self._get_stable_adk_user_id(email)
            
            # 2. 既存のADKセッションを整理
            self._cleanup_old_adk_sessions(adk_user_id)
            
            # 3. ログインセッションを作成
            login_session_id = self.login_session_manager.create_session(user_info, credentials)
            
            # 4. 統合セッション情報を構築
            unified_session = {
                "login_session_id": login_session_id,
                "adk_user_id": adk_user_id,
                "user_info": user_info,
                "created_at": time.time(),
                "status": "active",
                "adk_sessions_count": 0  # 実際のチャットセッション数は動的
            }
            
            logger.info(f"Created unified session - Login: {login_session_id}, ADK user: {adk_user_id}")
            return unified_session
            
        except Exception as e:
            logger.error(f"Failed to create unified session: {e}")
            raise
    
    def _cleanup_old_adk_sessions(self, adk_user_id: str, preserve_chat_history: bool = True):
        """指定ユーザーの古いADKセッションをクリーンアップ（チャット履歴保持オプション付き）"""
        try:
            # セッション同期マネージャーの機能を使用
            self.sync_manager._cleanup_adk_sessions_for_user(adk_user_id, preserve_chat_history)
                
        except Exception as e:
            logger.error(f"Failed to cleanup old ADK sessions: {e}")
    
    def get_unified_session_info(self, request: Request) -> Optional[Dict]:
        """リクエストから統合セッション情報を取得
        
        Args:
            request: FastAPIのRequestオブジェクト
            
        Returns:
            統合セッション情報またはNone
        """
        try:
            # ログインセッション情報を取得
            user_info = self.login_session_manager.get_user_info(request)
            if not user_info:
                return None
            
            # ADKユーザーIDを生成
            email = user_info.get("email")
            adk_user_id = self._get_stable_adk_user_id(email) if email else "anonymous"
            
            # 現在のADKセッション数を取得
            adk_sessions_count = self._get_adk_sessions_count(adk_user_id)
            
            # ログインセッションIDを取得
            login_session_id = self.login_session_manager.get_session_id_from_request(request)
            
            return {
                "login_session_id": login_session_id,
                "adk_user_id": adk_user_id,
                "user_info": user_info,
                "adk_sessions_count": adk_sessions_count,
                "status": "active"
            }
            
        except Exception as e:
            logger.error(f"Failed to get unified session info: {e}")
            return None
    
    def _get_adk_sessions_count(self, adk_user_id: str) -> int:
        """指定ユーザーのADKセッション数を取得"""
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (adk_user_id,))
            count = cursor.fetchone()[0]
            
            conn.close()
            return count
            
        except Exception as e:
            logger.error(f"Failed to get ADK sessions count: {e}")
            return 0
    
    def delete_unified_session(self, request: Request) -> bool:
        """統合セッションを完全削除
        
        Args:
            request: FastAPIのRequestオブジェクト
            
        Returns:
            削除成功かどうか
        """
        try:
            # 統合セッション情報を取得
            unified_info = self.get_unified_session_info(request)
            if not unified_info:
                logger.debug("No unified session found to delete")
                return True
            
            adk_user_id = unified_info["adk_user_id"]
            login_session_id = unified_info["login_session_id"]
            
            # ADKセッションを削除
            if adk_user_id != "anonymous":
                self._cleanup_old_adk_sessions(adk_user_id)
            
            # ログインセッションを削除
            if login_session_id:
                self.login_session_manager.delete_session(login_session_id)
            
            logger.info(f"Deleted unified session - Login: {login_session_id}, ADK user: {adk_user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete unified session: {e}")
            return False
    
    def get_adk_session_details(self, adk_user_id: str) -> List[Dict]:
        """指定ユーザーのADKセッション詳細を取得
        
        Args:
            adk_user_id: ADKユーザーID
            
        Returns:
            ADKセッション詳細のリスト
        """
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, app_name, state, create_time, update_time 
                FROM sessions 
                WHERE user_id = ? 
                ORDER BY update_time DESC
            """, (adk_user_id,))
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "session_id": row[0],
                    "app_name": row[1],
                    "state": row[2][:100] + "..." if len(row[2]) > 100 else row[2],  # 状態の一部
                    "created_at": row[3],
                    "updated_at": row[4]
                })
            
            conn.close()
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get ADK session details: {e}")
            return []
    
    def force_create_adk_session(self, adk_user_id: str, app_name: str = "document_creating_agent") -> str:
        """ADKセッションを強制作成（テスト用）
        
        Args:
            adk_user_id: ADKユーザーID
            app_name: アプリケーション名
            
        Returns:
            作成されたセッションID
        """
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            session_id = str(uuid.uuid4())
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                INSERT INTO sessions (app_name, user_id, id, state, create_time, update_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (app_name, adk_user_id, session_id, '{}', current_time, current_time))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Force created ADK session: {session_id} for user: {adk_user_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to force create ADK session: {e}")
            return ""
    
    def get_unified_stats(self) -> Dict:
        """統合セッション統計を取得
        
        Returns:
            統合統計情報
        """
        try:
            # ログインセッション統計
            login_stats = self.login_session_manager.get_session_stats()
            
            # ADKセッション統計
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(DISTINCT user_id) as total_users, COUNT(*) as total_sessions FROM sessions")
            adk_stats = cursor.fetchone()
            
            # ユーザー別ADKセッション数
            cursor.execute("""
                SELECT user_id, COUNT(*) as session_count 
                FROM sessions 
                GROUP BY user_id 
                ORDER BY session_count DESC
                LIMIT 10
            """)
            top_users = cursor.fetchall()
            
            conn.close()
            
            return {
                "login_sessions": login_stats,
                "adk_sessions": {
                    "total_users": adk_stats[0] if adk_stats else 0,
                    "total_sessions": adk_stats[1] if adk_stats else 0
                },
                "top_users": [
                    {"adk_user_id": row[0], "session_count": row[1]}
                    for row in top_users
                ],
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to get unified stats: {e}")
            return {"error": str(e)}
    
    def set_session_cookie(self, response: Response, request: Request):
        """統合セッション用のクッキーを設定
        
        Args:
            response: FastAPIのResponseオブジェクト
            request: FastAPIのRequestオブジェクト
        """
        try:
            unified_info = self.get_unified_session_info(request)
            if unified_info and unified_info.get("login_session_id"):
                self.login_session_manager.set_session_cookie(response, unified_info["login_session_id"])
        except Exception as e:
            logger.error(f"Failed to set session cookie: {e}")
    
    def clear_session_cookie(self, response: Response):
        """統合セッション用のクッキーを削除
        
        Args:
            response: FastAPIのResponseオブジェクト
        """
        self.login_session_manager.clear_session_cookie(response)

# グローバルインスタンス
_unified_session_manager = None

def get_unified_session_manager() -> UnifiedSessionManager:
    """統合セッション管理マネージャーのシングルトンインスタンスを取得"""
    global _unified_session_manager
    if _unified_session_manager is None:
        _unified_session_manager = UnifiedSessionManager()
    return _unified_session_manager