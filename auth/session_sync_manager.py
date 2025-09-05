"""
セッション同期管理システム
ログインセッション（ユーザー単位）とADKセッション（チャット単位）を同期
"""
import sqlite3
import logging
import hashlib
import time
from typing import Optional, Dict, List
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class SessionSyncManager:
    """ログインセッションとADKセッションの同期管理"""
    
    def __init__(self, adk_session_db_path: str = "sqlite:///./sessions.db"):
        self.adk_session_db_path = adk_session_db_path.replace('sqlite:///', '')
        
    def _get_stable_adk_user_id(self, email: str) -> str:
        """emailから安定したADKユーザーIDを生成"""
        if not email:
            return "anonymous"
        
        # 正規化して一貫性を保つ
        normalized_email = email.strip().lower()
        hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
        adk_user_id = hash_object.hexdigest()[:16]
        
        logger.debug(f"SessionSyncManager generated ADK user ID: {adk_user_id} for email: {normalized_email[:5]}...")
        
        return adk_user_id
    
    def _cleanup_adk_sessions_for_user(self, adk_user_id: str, preserve_chat_history: bool = True):
        """指定ユーザーの古いADKセッションをクリーンアップ（チャット履歴保持オプション付き）"""
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            # 該当ユーザーのセッション数を確認
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (adk_user_id,))
            session_count = cursor.fetchone()[0]
            
            if session_count > 0:
                logger.info(f"Cleaning up {session_count} existing ADK sessions for user: {adk_user_id} (preserve_history: {preserve_chat_history})")
                
                if preserve_chat_history:
                    # チャット履歴を保持してセッション情報のみ削除
                    
                    # 1. まずチャット履歴にarchive_timestampを追加（孤立化マーク）
                    archive_timestamp = time.time()
                    cursor.execute("""
                        UPDATE events 
                        SET grounding_metadata = COALESCE(grounding_metadata, '') || 
                            json_insert(
                                CASE WHEN grounding_metadata IS NULL OR grounding_metadata = '' 
                                     THEN '{}' 
                                     ELSE grounding_metadata 
                                END, 
                                '$.archived_at', ?
                            )
                        WHERE user_id = ? AND session_id IN (
                            SELECT id FROM sessions WHERE user_id = ?
                        )
                    """, (archive_timestamp, adk_user_id, adk_user_id))
                    
                    archived_events = cursor.rowcount
                    logger.info(f"Archived {archived_events} chat events for preservation")
                    
                    # 2. FOREIGN KEY制約を一時的に無効化
                    cursor.execute("PRAGMA foreign_keys = OFF")
                    
                    # 3. セッションのみ削除（eventsは残る）
                    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (adk_user_id,))
                    deleted_count = cursor.rowcount
                    
                    # 4. FOREIGN KEY制約を再有効化
                    cursor.execute("PRAGMA foreign_keys = ON")
                    
                    logger.info(f"Preserved chat history: archived {archived_events} events, deleted {deleted_count} sessions")
                else:
                    # 従来の動作：セッションとチャット履歴を完全削除
                    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (adk_user_id,))
                    deleted_count = cursor.rowcount
                    logger.info(f"Completely deleted {deleted_count} ADK sessions (including chat history)")
                
                conn.commit()
            else:
                logger.debug(f"No existing ADK sessions found for user: {adk_user_id}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup ADK sessions for user {adk_user_id}: {e}")
            if 'conn' in locals():
                conn.rollback()
        finally:
            if 'conn' in locals():
                conn.close()
    
    def on_login(self, user_info: dict, credentials: Credentials) -> tuple[str, str]:
        """ログイン時の同期処理
        
        Args:
            user_info: ユーザー情報（email含む）
            credentials: OAuth認証情報
            
        Returns:
            tuple[login_session_id, adk_user_id]: ログインセッションIDとADKユーザーID
        """
        try:
            email = user_info.get("email")
            if not email:
                raise ValueError("User email is required for session sync")
            
            # ADK用の安定したユーザーIDを生成
            adk_user_id = self._get_stable_adk_user_id(email)
            
            # 1. 既存のADKセッションをクリーンアップ
            self._cleanup_adk_sessions_for_user(adk_user_id)
            
            # 2. ログインセッションを作成
            from auth.session_auth import get_session_auth_manager
            session_manager = get_session_auth_manager()
            login_session_id = session_manager.create_session(user_info, credentials)
            
            logger.info(f"Login sync completed - Login session: {login_session_id}, ADK user: {adk_user_id}")
            return login_session_id, adk_user_id
            
        except Exception as e:
            logger.error(f"Failed to sync login session: {e}")
            raise
    
    def on_logout(self, login_session_id: str, adk_user_id: Optional[str] = None):
        """ログアウト時の同期処理
        
        Args:
            login_session_id: ログインセッションID
            adk_user_id: ADKユーザーID（指定されない場合は推測）
        """
        try:
            # 1. ログインセッション情報を取得してADKユーザーIDを推測
            if not adk_user_id:
                from auth.session_auth import get_session_auth_manager
                session_manager = get_session_auth_manager()
                session_data = session_manager.get_session(login_session_id)
                if session_data and session_data.get('user_info'):
                    email = session_data['user_info'].get('email')
                    if email:
                        adk_user_id = self._get_stable_adk_user_id(email)
            
            # 2. ADKセッションをクリーンアップ
            if adk_user_id and adk_user_id != "anonymous":
                self._cleanup_adk_sessions_for_user(adk_user_id)
                logger.info(f"Logout sync completed - Cleaned ADK sessions for user: {adk_user_id}")
            
            # 3. ログインセッションは呼び出し元で削除される
                
        except Exception as e:
            logger.error(f"Failed to sync logout session: {e}")
            # ログアウト時のエラーは継続処理
    
    def get_session_stats(self, adk_user_id: Optional[str] = None) -> Dict:
        """セッション統計情報を取得
        
        Args:
            adk_user_id: 特定ユーザーの統計（指定しない場合は全体）
            
        Returns:
            統計情報の辞書
        """
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            stats = {}
            
            # 全体統計
            cursor.execute("SELECT COUNT(DISTINCT user_id) as total_users, COUNT(*) as total_sessions FROM sessions")
            total_stats = cursor.fetchone()
            stats["total_adk_users"] = total_stats[0] if total_stats else 0
            stats["total_adk_sessions"] = total_stats[1] if total_stats else 0
            
            # 特定ユーザーの統計
            if adk_user_id:
                cursor.execute("""
                    SELECT COUNT(*) as user_sessions, MAX(update_time) as last_activity 
                    FROM sessions 
                    WHERE user_id = ?
                """, (adk_user_id,))
                user_stats = cursor.fetchone()
                stats["user_adk_sessions"] = user_stats[0] if user_stats else 0
                stats["user_last_activity"] = user_stats[1] if user_stats else None
            
            # ログインセッション統計
            from auth.session_auth import get_session_auth_manager
            session_manager = get_session_auth_manager()
            login_stats = session_manager.get_session_stats()
            stats.update(login_stats)
            
            conn.close()
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")
            return {"error": str(e)}
    
    def cleanup_orphaned_adk_sessions(self) -> int:
        """孤立したADKセッション（対応するログインセッションがない）をクリーンアップ
        
        Returns:
            削除されたセッション数
        """
        try:
            # 現在のログインセッションからアクティブユーザーIDを取得
            from auth.session_auth import get_session_auth_manager
            session_manager = get_session_auth_manager()
            
            # すべてのログインセッションからemailを抽出
            active_adk_user_ids = set()
            for session_data in session_manager._sessions.values():
                user_info = session_data.get('user_info', {})
                email = user_info.get('email')
                if email:
                    adk_user_id = self._get_stable_adk_user_id(email)
                    active_adk_user_ids.add(adk_user_id)
            
            # ADKセッションのユーザーIDを取得
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT DISTINCT user_id FROM sessions")
            all_adk_user_ids = {row[0] for row in cursor.fetchall()}
            
            # 孤立したユーザーIDを特定
            orphaned_user_ids = all_adk_user_ids - active_adk_user_ids
            orphaned_user_ids.discard("anonymous")  # anonymousは除外
            
            deleted_count = 0
            for user_id in orphaned_user_ids:
                cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
                deleted_count += cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} orphaned ADK sessions")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned ADK sessions: {e}")
            return 0
    
    def get_archived_chat_history(self, adk_user_id: str, limit: int = 50) -> List[Dict]:
        """指定ユーザーのアーカイブされたチャット履歴を取得
        
        Args:
            adk_user_id: ADKユーザーID
            limit: 取得する最大件数
            
        Returns:
            アーカイブされたチャット履歴のリスト
        """
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    session_id,
                    timestamp,
                    author,
                    content,
                    grounding_metadata,
                    turn_complete
                FROM events 
                WHERE user_id = ? 
                  AND grounding_metadata LIKE '%archived_at%'
                ORDER BY timestamp DESC
                LIMIT ?
            """, (adk_user_id, limit))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    "session_id": row[0],
                    "timestamp": row[1],
                    "author": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "turn_complete": row[5]
                })
            
            conn.close()
            
            logger.info(f"Retrieved {len(history)} archived chat entries for user: {adk_user_id}")
            return history
            
        except Exception as e:
            logger.error(f"Failed to get archived chat history: {e}")
            return []
    
    def cleanup_old_archived_chats(self, days_to_keep: int = 90) -> int:
        """古いアーカイブチャットを削除
        
        Args:
            days_to_keep: 保持する日数
            
        Returns:
            削除されたチャット数
        """
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            # X日前のタイムスタンプを計算
            cutoff_timestamp = time.time() - (days_to_keep * 24 * 60 * 60)
            
            # 古いアーカイブチャットを削除
            cursor.execute("""
                DELETE FROM events 
                WHERE grounding_metadata LIKE '%archived_at%'
                  AND json_extract(grounding_metadata, '$.archived_at') < ?
            """, (cutoff_timestamp,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old archived chats (older than {days_to_keep} days)")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old archived chats: {e}")
            return 0
    
    def get_archived_chat_stats(self) -> Dict:
        """アーカイブチャットの統計情報を取得"""
        try:
            conn = sqlite3.connect(self.adk_session_db_path)
            cursor = conn.cursor()
            
            # アーカイブチャット統計
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_archived,
                    COUNT(DISTINCT user_id) as users_with_archives,
                    COUNT(DISTINCT session_id) as archived_sessions,
                    MIN(timestamp) as oldest_archive,
                    MAX(timestamp) as newest_archive
                FROM events 
                WHERE grounding_metadata LIKE '%archived_at%'
            """)
            
            stats = cursor.fetchone()
            
            # ユーザー別統計
            cursor.execute("""
                SELECT user_id, COUNT(*) as event_count
                FROM events 
                WHERE grounding_metadata LIKE '%archived_at%'
                GROUP BY user_id
                ORDER BY event_count DESC
                LIMIT 10
            """)
            
            user_stats = cursor.fetchall()
            
            conn.close()
            
            return {
                "total_archived_events": stats[0] if stats else 0,
                "users_with_archives": stats[1] if stats else 0,
                "archived_sessions": stats[2] if stats else 0,
                "oldest_archive": stats[3] if stats else None,
                "newest_archive": stats[4] if stats else None,
                "top_users": [
                    {"user_id": row[0], "archived_events": row[1]}
                    for row in user_stats
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get archived chat stats: {e}")
            return {"error": str(e)}

# グローバルインスタンス
_session_sync_manager = None

def get_session_sync_manager() -> SessionSyncManager:
    """セッション同期マネージャーのシングルトンインスタンスを取得"""
    global _session_sync_manager
    if _session_sync_manager is None:
        _session_sync_manager = SessionSyncManager()
    return _session_sync_manager