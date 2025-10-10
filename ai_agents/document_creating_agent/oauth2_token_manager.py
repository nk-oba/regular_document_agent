"""
OAuth2トークン管理モジュール

OAuth2トークン情報をメモリキャッシュで管理し、
ファイルI/Oを最小限に抑えることでパフォーマンスを向上させる。
"""
import logging
import time
import threading
import json
import os
from typing import Optional, Dict
from pathlib import Path
from dataclasses import dataclass, asdict
from google.adk.auth import OAuth2Auth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """OAuth2トークン情報を保持するデータクラス"""
    user_id: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[int]
    client_id: str
    client_secret: str
    token_uri: str
    cached_at: float  # キャッシュされた時刻

    def is_expired(self) -> bool:
        """
        トークンが期限切れかチェック

        Returns:
            bool: 期限切れの場合True
        """
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at

    def needs_refresh(self, buffer_seconds: int = 300) -> bool:
        """
        トークンの更新が必要かチェック（5分前にリフレッシュ）

        Args:
            buffer_seconds: 有効期限前のバッファ時間（秒）

        Returns:
            bool: 更新が必要な場合True
        """
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - buffer_seconds)

    def to_oauth2_auth(self) -> OAuth2Auth:
        """OAuth2Authオブジェクトに変換"""
        return OAuth2Auth(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
            client_id=self.client_id,
            client_secret=self.client_secret
        )


class OAuth2TokenManager:
    """
    OAuth2トークンを管理するシングルトンクラス

    トークン情報をメモリにキャッシュし、ファイルI/Oを最小化。
    自動的にトークンをリフレッシュし、有効なトークンを提供する。
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

        self._tokens: Dict[str, TokenInfo] = {}
        self._token_lock = threading.Lock()
        self._auth_dir = Path("auth_storage/mcp_ada_auth")
        self._token_uri = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token"
        self._initialized = True
        logger.info("[OAuth2TokenManager] Initialized")

    def _get_oauth2_file_path(self, user_id: str) -> Path:
        """
        OAuth2認証ファイルのパスを取得

        Args:
            user_id: Google User ID

        Returns:
            Path: OAuth2認証ファイルのパス
        """
        return self._auth_dir / f"mcp_ada_oauth2_auth_{user_id}.json"

    def _load_from_file(self, user_id: str) -> Optional[TokenInfo]:
        """
        ファイルからトークン情報を読み込み

        Args:
            user_id: Google User ID

        Returns:
            Optional[TokenInfo]: トークン情報、失敗時はNone
        """
        oauth2_file = self._get_oauth2_file_path(user_id)

        if not oauth2_file.exists():
            logger.debug(f"[OAuth2TokenManager] No OAuth2 file found for user: {user_id}")
            return None

        try:
            with open(oauth2_file, 'r') as f:
                oauth2_data = json.load(f)

            token_info = TokenInfo(
                user_id=user_id,
                access_token=oauth2_data.get('access_token', ''),
                refresh_token=oauth2_data.get('refresh_token'),
                expires_at=oauth2_data.get('expires_at'),
                client_id=oauth2_data.get('client_id', ''),
                client_secret=oauth2_data.get('client_secret', ''),
                token_uri=self._token_uri,
                cached_at=time.time()
            )

            logger.debug(f"[OAuth2TokenManager] Loaded token from file for user: {user_id}")
            return token_info

        except json.JSONDecodeError as e:
            logger.error(f"[OAuth2TokenManager] Failed to parse OAuth2 file for {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"[OAuth2TokenManager] Failed to load token from file for {user_id}: {e}")
            return None

    def _save_to_file(self, token_info: TokenInfo) -> bool:
        """
        トークン情報をファイルに保存

        Args:
            token_info: トークン情報

        Returns:
            bool: 成功時True
        """
        oauth2_file = self._get_oauth2_file_path(token_info.user_id)

        try:
            # ディレクトリが存在しない場合は作成
            oauth2_file.parent.mkdir(parents=True, exist_ok=True)

            oauth2_data = {
                'access_token': token_info.access_token,
                'refresh_token': token_info.refresh_token,
                'expires_at': token_info.expires_at,
                'client_id': token_info.client_id,
                'client_secret': token_info.client_secret
            }

            with open(oauth2_file, 'w') as f:
                json.dump(oauth2_data, f, indent=2)

            logger.debug(f"[OAuth2TokenManager] Saved token to file for user: {token_info.user_id}")
            return True

        except Exception as e:
            logger.error(f"[OAuth2TokenManager] Failed to save token to file for {token_info.user_id}: {e}")
            return False

    def _refresh_token(self, token_info: TokenInfo) -> Optional[TokenInfo]:
        """
        トークンをリフレッシュ

        Args:
            token_info: 現在のトークン情報

        Returns:
            Optional[TokenInfo]: 更新されたトークン情報、失敗時はNone
        """
        if not token_info.refresh_token:
            logger.error(f"[OAuth2TokenManager] No refresh token available for user: {token_info.user_id}")
            return None

        try:
            logger.info(f"[OAuth2TokenManager] Refreshing token for user: {token_info.user_id}")

            # Google OAuth2ライブラリを使用してトークン更新
            creds = Credentials(
                token=token_info.access_token,
                refresh_token=token_info.refresh_token,
                token_uri=token_info.token_uri,
                client_id=token_info.client_id,
                client_secret=token_info.client_secret
            )

            creds.refresh(GoogleAuthRequest())

            # 新しいトークン情報を作成
            new_token_info = TokenInfo(
                user_id=token_info.user_id,
                access_token=creds.token,
                refresh_token=token_info.refresh_token,  # refresh_tokenは通常変わらない
                expires_at=int(creds.expiry.timestamp()) if creds.expiry else None,
                client_id=token_info.client_id,
                client_secret=token_info.client_secret,
                token_uri=token_info.token_uri,
                cached_at=time.time()
            )

            logger.info(f"[OAuth2TokenManager] ✓ Token refreshed for user: {token_info.user_id}")
            return new_token_info

        except Exception as e:
            logger.error(f"[OAuth2TokenManager] Failed to refresh token for {token_info.user_id}: {e}")
            import traceback
            logger.debug(f"[OAuth2TokenManager] Exception: {traceback.format_exc()}")
            return None

    def get_token(self, user_id: str, auto_refresh: bool = True) -> Optional[str]:
        """
        ユーザーの有効なアクセストークンを取得

        Args:
            user_id: Google User ID
            auto_refresh: 自動的にトークンをリフレッシュするか

        Returns:
            Optional[str]: 有効なアクセストークン、失敗時はNone
        """
        with self._token_lock:
            # キャッシュをチェック
            token_info = self._tokens.get(user_id)

            # キャッシュにない場合はファイルから読み込み
            if token_info is None:
                logger.debug(f"[OAuth2TokenManager] Token not in cache, loading from file for user: {user_id}")
                token_info = self._load_from_file(user_id)

                if token_info is None:
                    logger.warning(f"[OAuth2TokenManager] No token found for user: {user_id}")
                    return None

                # キャッシュに保存
                self._tokens[user_id] = token_info
                logger.debug(f"[OAuth2TokenManager] Token cached for user: {user_id}")

            # トークンの有効期限をチェック
            if auto_refresh and token_info.needs_refresh():
                logger.info(f"[OAuth2TokenManager] Token needs refresh for user: {user_id}")
                new_token_info = self._refresh_token(token_info)

                if new_token_info is None:
                    logger.error(f"[OAuth2TokenManager] Failed to refresh token for user: {user_id}")
                    return None

                # キャッシュとファイルを更新
                self._tokens[user_id] = new_token_info
                self._save_to_file(new_token_info)
                token_info = new_token_info

            logger.debug(f"[OAuth2TokenManager] Returning valid token for user: {user_id}")
            return token_info.access_token

    def get_token_info(self, user_id: str, auto_refresh: bool = True) -> Optional[TokenInfo]:
        """
        ユーザーのトークン情報を取得（詳細情報が必要な場合）

        Args:
            user_id: Google User ID
            auto_refresh: 自動的にトークンをリフレッシュするか

        Returns:
            Optional[TokenInfo]: トークン情報、失敗時はNone
        """
        # get_tokenを呼び出してトークンを取得・更新
        access_token = self.get_token(user_id, auto_refresh)
        if access_token is None:
            return None

        with self._token_lock:
            return self._tokens.get(user_id)

    def invalidate_token(self, user_id: str):
        """
        ユーザーのトークンキャッシュを無効化

        Args:
            user_id: Google User ID
        """
        with self._token_lock:
            if user_id in self._tokens:
                del self._tokens[user_id]
                logger.info(f"[OAuth2TokenManager] Token invalidated for user: {user_id}")

    def force_refresh(self, user_id: str) -> Optional[str]:
        """
        トークンを強制的にリフレッシュ

        Args:
            user_id: Google User ID

        Returns:
            Optional[str]: 新しいアクセストークン、失敗時はNone
        """
        with self._token_lock:
            # まずキャッシュまたはファイルからトークン情報を取得
            token_info = self._tokens.get(user_id)
            if token_info is None:
                token_info = self._load_from_file(user_id)
                if token_info is None:
                    logger.error(f"[OAuth2TokenManager] No token to refresh for user: {user_id}")
                    return None

            # リフレッシュを実行
            new_token_info = self._refresh_token(token_info)
            if new_token_info is None:
                return None

            # キャッシュとファイルを更新
            self._tokens[user_id] = new_token_info
            self._save_to_file(new_token_info)

            return new_token_info.access_token

    def cleanup_expired_tokens(self):
        """期限切れトークンのキャッシュをクリーンアップ"""
        with self._token_lock:
            expired_users = [
                user_id
                for user_id, token_info in self._tokens.items()
                if token_info.is_expired() and not token_info.refresh_token
            ]

            for user_id in expired_users:
                del self._tokens[user_id]
                logger.debug(f"[OAuth2TokenManager] Cleaned up expired token for user: {user_id}")

            if expired_users:
                logger.info(
                    f"[OAuth2TokenManager] Cleaned up {len(expired_users)} expired token(s)"
                )

    def get_stats(self) -> Dict[str, any]:
        """
        トークン管理の統計情報を取得

        Returns:
            Dict: 統計情報
        """
        with self._token_lock:
            total_tokens = len(self._tokens)
            expired_tokens = sum(
                1 for token_info in self._tokens.values()
                if token_info.is_expired()
            )
            needs_refresh = sum(
                1 for token_info in self._tokens.values()
                if token_info.needs_refresh()
            )

            return {
                "total_cached_tokens": total_tokens,
                "expired_tokens": expired_tokens,
                "needs_refresh": needs_refresh,
                "valid_tokens": total_tokens - expired_tokens
            }


# グローバルインスタンス
_token_manager = OAuth2TokenManager()


def get_token_manager() -> OAuth2TokenManager:
    """
    OAuth2トークンマネージャーのグローバルインスタンスを取得

    Returns:
        OAuth2TokenManager: シングルトンインスタンス
    """
    return _token_manager
