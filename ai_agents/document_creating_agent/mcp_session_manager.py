"""
MCPセッション管理モジュール

MCPサーバーとのセッションをユーザーごとにキャッシュし、
再利用することでパフォーマンスを向上させる。
"""
import logging
import time
import threading
from typing import Optional, Dict
from dataclasses import dataclass
import requests

logger = logging.getLogger(__name__)


@dataclass
class MCPSession:
    """MCPセッション情報を保持するデータクラス"""
    session_id: str
    user_id: str
    created_at: float
    last_used_at: float
    mcp_server_url: str

    def is_expired(self, ttl_seconds: int = 1800) -> bool:
        """
        セッションが有効期限切れかチェック

        Args:
            ttl_seconds: セッションの有効期間（秒）、デフォルト30分

        Returns:
            bool: 期限切れの場合True
        """
        return (time.time() - self.created_at) > ttl_seconds

    def update_last_used(self):
        """最終使用時刻を更新"""
        self.last_used_at = time.time()


class MCPSessionManager:
    """
    MCPセッションを管理するシングルトンクラス

    ユーザーごとにセッションIDをキャッシュし、
    有効期限内であれば再利用することでパフォーマンスを向上させる。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """シングルトンパターンの実装"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初期化（一度だけ実行される）"""
        if self._initialized:
            return

        self._sessions: Dict[str, MCPSession] = {}
        self._session_lock = threading.Lock()
        self._session_ttl = 1800  # デフォルト30分
        self._initialized = True
        logger.info("[MCPSessionManager] Initialized")

    def set_session_ttl(self, ttl_seconds: int):
        """
        セッションの有効期間を設定

        Args:
            ttl_seconds: 有効期間（秒）
        """
        self._session_ttl = ttl_seconds
        logger.info(f"[MCPSessionManager] Session TTL set to {ttl_seconds} seconds")

    def get_session(self, user_id: str, mcp_server_url: str) -> Optional[str]:
        """
        ユーザーの有効なセッションIDを取得

        Args:
            user_id: Google User ID
            mcp_server_url: MCPサーバーのURL

        Returns:
            Optional[str]: 有効なセッションID、存在しない場合はNone
        """
        with self._session_lock:
            session = self._sessions.get(user_id)

            if session is None:
                logger.debug(f"[MCPSessionManager] No cached session for user: {user_id}")
                return None

            # セッションが期限切れかチェック
            if session.is_expired(self._session_ttl):
                logger.info(f"[MCPSessionManager] Session expired for user: {user_id}")
                del self._sessions[user_id]
                return None

            # サーバーURLが一致するかチェック
            if session.mcp_server_url != mcp_server_url:
                logger.warning(
                    f"[MCPSessionManager] Server URL mismatch for user {user_id}: "
                    f"cached={session.mcp_server_url}, requested={mcp_server_url}"
                )
                del self._sessions[user_id]
                return None

            # 最終使用時刻を更新
            session.update_last_used()
            logger.info(
                f"[MCPSessionManager] Reusing cached session for user: {user_id}, "
                f"session_id: {session.session_id[:16]}..."
            )
            return session.session_id

    def create_session(
        self,
        user_id: str,
        access_token: str,
        mcp_server_url: str,
        timeout: int = 30
    ) -> Optional[str]:
        """
        新しいMCPセッションを作成してキャッシュ

        Args:
            user_id: Google User ID
            access_token: OAuth2アクセストークン
            mcp_server_url: MCPサーバーのURL
            timeout: リクエストタイムアウト（秒）

        Returns:
            Optional[str]: 作成されたセッションID、失敗した場合はNone
        """
        logger.info(f"[MCPSessionManager] Creating new MCP session for user: {user_id}")

        try:
            # MCP初期化リクエスト
            init_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }

            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "document_creating_agent",
                        "version": "1.0.0"
                    }
                }
            }

            logger.debug(f"[MCPSessionManager] Sending initialization request to {mcp_server_url}/mcp")
            response = requests.post(
                f"{mcp_server_url}/mcp",
                headers=init_headers,
                json=init_request,
                timeout=timeout
            )

            if response.status_code != 200:
                response.encoding = 'utf-8'
                logger.error(
                    f"[MCPSessionManager] MCP initialization failed: "
                    f"{response.status_code} - {response.text}"
                )
                return None

            # セッションIDをレスポンスヘッダーから取得
            session_id = response.headers.get('mcp-session-id')
            if not session_id:
                logger.error("[MCPSessionManager] No session ID returned from MCP server")
                logger.debug(f"[MCPSessionManager] Response headers: {dict(response.headers)}")
                return None

            # セッションをキャッシュ
            with self._session_lock:
                current_time = time.time()
                session = MCPSession(
                    session_id=session_id,
                    user_id=user_id,
                    created_at=current_time,
                    last_used_at=current_time,
                    mcp_server_url=mcp_server_url
                )
                self._sessions[user_id] = session

            logger.info(
                f"[MCPSessionManager] ✓ Session created and cached for user: {user_id}, "
                f"session_id: {session_id[:16]}..."
            )
            return session_id

        except requests.exceptions.Timeout:
            logger.error(f"[MCPSessionManager] MCP initialization timeout for user: {user_id}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[MCPSessionManager] MCP initialization request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"[MCPSessionManager] Unexpected error creating session: {e}")
            import traceback
            logger.debug(f"[MCPSessionManager] Exception: {traceback.format_exc()}")
            return None

    def get_or_create_session(
        self,
        user_id: str,
        access_token: str,
        mcp_server_url: str,
        timeout: int = 30
    ) -> Optional[str]:
        """
        有効なセッションを取得、存在しない場合は新規作成

        Args:
            user_id: Google User ID
            access_token: OAuth2アクセストークン
            mcp_server_url: MCPサーバーのURL
            timeout: リクエストタイムアウト（秒）

        Returns:
            Optional[str]: セッションID、失敗した場合はNone
        """
        # まずキャッシュをチェック
        session_id = self.get_session(user_id, mcp_server_url)
        if session_id:
            return session_id

        # キャッシュになければ新規作成
        return self.create_session(user_id, access_token, mcp_server_url, timeout)

    def invalidate_session(self, user_id: str):
        """
        ユーザーのセッションを無効化

        Args:
            user_id: Google User ID
        """
        with self._session_lock:
            if user_id in self._sessions:
                del self._sessions[user_id]
                logger.info(f"[MCPSessionManager] Session invalidated for user: {user_id}")

    def cleanup_expired_sessions(self):
        """期限切れセッションをクリーンアップ"""
        with self._session_lock:
            expired_users = [
                user_id
                for user_id, session in self._sessions.items()
                if session.is_expired(self._session_ttl)
            ]

            for user_id in expired_users:
                del self._sessions[user_id]
                logger.debug(f"[MCPSessionManager] Cleaned up expired session for user: {user_id}")

            if expired_users:
                logger.info(
                    f"[MCPSessionManager] Cleaned up {len(expired_users)} expired session(s)"
                )

    def get_stats(self) -> Dict[str, any]:
        """
        セッション管理の統計情報を取得

        Returns:
            Dict: 統計情報
        """
        with self._session_lock:
            total_sessions = len(self._sessions)
            expired_sessions = sum(
                1 for session in self._sessions.values()
                if session.is_expired(self._session_ttl)
            )

            return {
                "total_sessions": total_sessions,
                "active_sessions": total_sessions - expired_sessions,
                "expired_sessions": expired_sessions,
                "session_ttl": self._session_ttl
            }


# グローバルインスタンス
_session_manager = MCPSessionManager()


def get_session_manager() -> MCPSessionManager:
    """
    MCPセッションマネージャーのグローバルインスタンスを取得

    Returns:
        MCPSessionManager: シングルトンインスタンス
    """
    return _session_manager
