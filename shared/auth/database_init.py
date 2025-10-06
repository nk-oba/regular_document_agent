"""
認証データベース初期化モジュール
auth_sessions.dbの作成とテーブル初期化を管理
"""
import sqlite3
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class AuthDatabaseInitializer:
    """認証データベースの初期化を管理するクラス"""
    
    def __init__(self, db_path: str = "auth_storage/auth_sessions.db"):
        self.db_path = db_path
        self.db_dir = Path(db_path).parent
        
    def initialize_database(self) -> bool:
        """データベースとテーブルを初期化"""
        try:
            # ディレクトリを作成
            self.db_dir.mkdir(parents=True, exist_ok=True)
            
            # データベース接続
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # テーブル作成
            self._create_login_sessions_table(cursor)
            self._create_adk_sessions_table(cursor)
            
            # インデックス作成
            self._create_indexes(cursor)
            
            conn.commit()
            conn.close()
            
            logger.info(f"Auth database initialized successfully: {self.db_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize auth database: {e}")
            return False
    
    def _create_login_sessions_table(self, cursor):
        """ログインセッションテーブルを作成"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_sessions (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                user_info TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        logger.debug("Created login_sessions table")
    
    def _create_adk_sessions_table(self, cursor):
        """ADKセッション関連テーブルを作成"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS adk_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login_session_id TEXT NOT NULL,
                adk_user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (login_session_id) REFERENCES login_sessions(id) ON DELETE CASCADE,
                UNIQUE(login_session_id, adk_user_id)
            )
        """)
        logger.debug("Created adk_sessions table")
    
    def _create_indexes(self, cursor):
        """インデックスを作成"""
        # ログインセッション用インデックス
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_login_sessions_email 
            ON login_sessions(email)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_login_sessions_expires 
            ON login_sessions(expires_at)
        """)
        
        # ADKセッション用インデックス
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_adk_sessions_login_id 
            ON adk_sessions(login_session_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_adk_sessions_adk_user_id 
            ON adk_sessions(adk_user_id)
        """)
        
        logger.debug("Created database indexes")
    
    def is_database_initialized(self) -> bool:
        """データベースが初期化済みかチェック"""
        try:
            if not os.path.exists(self.db_path):
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # テーブル存在チェック
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name IN ('login_sessions', 'adk_sessions')
            """)
            
            tables = cursor.fetchall()
            conn.close()
            
            return len(tables) == 2
            
        except Exception as e:
            logger.error(f"Failed to check database initialization: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """期限切れセッションをクリーンアップ"""
        try:
            import time
            current_time = time.time()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 期限切れログインセッションを削除
            cursor.execute("""
                DELETE FROM login_sessions 
                WHERE expires_at < ?
            """, (current_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired login sessions")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")
            return 0

# グローバルインスタンス
_auth_db_initializer = None

def get_auth_database_initializer() -> AuthDatabaseInitializer:
    """認証データベース初期化器のシングルトンインスタンスを取得"""
    global _auth_db_initializer
    if _auth_db_initializer is None:
        _auth_db_initializer = AuthDatabaseInitializer()
    return _auth_db_initializer

def ensure_auth_database_initialized() -> bool:
    """認証データベースが初期化されていることを保証"""
    initializer = get_auth_database_initializer()
    
    if not initializer.is_database_initialized():
        logger.info("Auth database not initialized, creating...")
        return initializer.initialize_database()
    
    return True


