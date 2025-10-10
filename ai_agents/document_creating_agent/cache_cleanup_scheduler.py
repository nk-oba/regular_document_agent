"""
キャッシュクリーンアップスケジューラー

MCPセッションとOAuth2トークンのキャッシュを定期的にクリーンアップする。
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CacheCleanupScheduler:
    """
    キャッシュクリーンアップを定期的に実行するスケジューラー
    """

    def __init__(self, cleanup_interval: int = 3600):
        """
        初期化

        Args:
            cleanup_interval: クリーンアップ間隔（秒）、デフォルト1時間
        """
        self._cleanup_interval = cleanup_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        logger.info(f"[CacheCleanupScheduler] Initialized with interval: {cleanup_interval}s")

    def start(self):
        """クリーンアップスケジューラーを開始"""
        if self._running:
            logger.warning("[CacheCleanupScheduler] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info("[CacheCleanupScheduler] Started")

    def stop(self):
        """クリーンアップスケジューラーを停止"""
        if not self._running:
            logger.warning("[CacheCleanupScheduler] Not running")
            return

        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[CacheCleanupScheduler] Stopped")

    def _cleanup_loop(self):
        """クリーンアップループ（バックグラウンドスレッドで実行）"""
        logger.info("[CacheCleanupScheduler] Cleanup loop started")

        while self._running:
            try:
                # クリーンアップ実行
                self._perform_cleanup()

                # 次のクリーンアップまで待機
                time.sleep(self._cleanup_interval)

            except Exception as e:
                logger.error(f"[CacheCleanupScheduler] Error in cleanup loop: {e}")
                import traceback
                logger.debug(f"[CacheCleanupScheduler] Exception: {traceback.format_exc()}")
                # エラーが発生しても継続
                time.sleep(60)  # エラー時は1分待機

        logger.info("[CacheCleanupScheduler] Cleanup loop ended")

    def _perform_cleanup(self):
        """クリーンアップを実行"""
        try:
            from .mcp_session_manager import get_session_manager
            from .oauth2_token_manager import get_token_manager

            logger.debug("[CacheCleanupScheduler] Starting cleanup")

            # セッションキャッシュのクリーンアップ
            session_manager = get_session_manager()
            session_stats_before = session_manager.get_stats()
            session_manager.cleanup_expired_sessions()
            session_stats_after = session_manager.get_stats()

            logger.info(
                f"[CacheCleanupScheduler] Session cleanup completed: "
                f"{session_stats_before['total_sessions']} -> {session_stats_after['total_sessions']} sessions"
            )

            # トークンキャッシュのクリーンアップ
            token_manager = get_token_manager()
            token_stats_before = token_manager.get_stats()
            token_manager.cleanup_expired_tokens()
            token_stats_after = token_manager.get_stats()

            logger.info(
                f"[CacheCleanupScheduler] Token cleanup completed: "
                f"{token_stats_before['total_cached_tokens']} -> {token_stats_after['total_cached_tokens']} tokens"
            )

        except Exception as e:
            logger.error(f"[CacheCleanupScheduler] Error during cleanup: {e}")
            import traceback
            logger.debug(f"[CacheCleanupScheduler] Exception: {traceback.format_exc()}")

    def trigger_cleanup(self):
        """手動でクリーンアップをトリガー"""
        logger.info("[CacheCleanupScheduler] Manual cleanup triggered")
        self._perform_cleanup()


# グローバルインスタンス
_scheduler: Optional[CacheCleanupScheduler] = None
_scheduler_lock = threading.Lock()


def get_cleanup_scheduler(cleanup_interval: int = 3600) -> CacheCleanupScheduler:
    """
    クリーンアップスケジューラーのグローバルインスタンスを取得

    Args:
        cleanup_interval: クリーンアップ間隔（秒）

    Returns:
        CacheCleanupScheduler: シングルトンインスタンス
    """
    global _scheduler

    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = CacheCleanupScheduler(cleanup_interval)

    return _scheduler


def start_cache_cleanup(cleanup_interval: int = 3600):
    """
    キャッシュクリーンアップを開始

    Args:
        cleanup_interval: クリーンアップ間隔（秒）、デフォルト1時間
    """
    scheduler = get_cleanup_scheduler(cleanup_interval)
    scheduler.start()


def stop_cache_cleanup():
    """キャッシュクリーンアップを停止"""
    global _scheduler

    if _scheduler:
        _scheduler.stop()
