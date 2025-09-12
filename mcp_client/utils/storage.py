"""
セキュアストレージ
トークンの安全な永続化とマルチユーザー対応
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from .crypto import CryptoUtils
import logging

logger = logging.getLogger(__name__)


class SecureStorage:
    """セキュアストレージクラス
    
    暗号化されたトークンデータの永続化とマルチユーザー対応
    """
    
    def __init__(self, base_path: Optional[str] = None, crypto_password: Optional[str] = None):
        """セキュアストレージを初期化
        
        Args:
            base_path: ベースディレクトリパス。Noneの場合はデフォルトを使用
            crypto_password: 暗号化パスワード。Noneの場合は環境変数から取得
        """
        # ベースパスの設定
        if base_path is None:
            base_path = os.path.join(os.path.expanduser('~'), '.mcp_client')
        
        self.base_path = Path(base_path)
        self.tokens_dir = self.base_path / 'tokens'
        self.clients_dir = self.base_path / 'clients'
        
        # ディレクトリの作成
        self._ensure_directories()
        
        # 暗号化ユーティリティ
        self.crypto = CryptoUtils(crypto_password)
        
        logger.info(f"SecureStorage initialized at: {self.base_path}")
    
    def _ensure_directories(self) -> None:
        """必要なディレクトリを作成"""
        directories = [self.base_path, self.tokens_dir, self.clients_dir]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            
            # ディレクトリのパーミッションを制限（Unix系のみ）
            if os.name != 'nt':  # Windows以外
                os.chmod(directory, 0o700)  # ユーザーのみアクセス可能
    
    def _get_token_file_path(self, server_url: str, user_id: Optional[str] = None) -> Path:
        """トークンファイルのパスを生成
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID（Noneの場合は'default'）
            
        Returns:
            Path: トークンファイルのパス
        """
        # URLを安全なファイル名に変換
        safe_server_name = self._safe_filename(server_url)
        user_part = user_id if user_id else 'default'
        
        filename = f"{safe_server_name}_{user_part}_tokens.enc"
        return self.tokens_dir / filename
    
    def _get_client_file_path(self, server_url: str, user_id: Optional[str] = None) -> Path:
        """クライアント認証情報ファイルのパスを生成
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID（Noneの場合は'default'）
            
        Returns:
            Path: クライアント認証情報ファイルのパス
        """
        safe_server_name = self._safe_filename(server_url)
        user_part = user_id if user_id else 'default'
        
        filename = f"{safe_server_name}_{user_part}_client.enc"
        return self.clients_dir / filename
    
    def _safe_filename(self, url: str) -> str:
        """URLを安全なファイル名に変換
        
        Args:
            url: 変換対象のURL
            
        Returns:
            str: 安全なファイル名
        """
        import re
        
        # プロトコルを除去
        filename = re.sub(r'^https?://', '', url)
        # 安全でない文字を置換
        filename = re.sub(r'[^\w\-_.]', '_', filename)
        # 長すぎる場合は切り詰め
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename
    
    def save_token_data(
        self, 
        server_url: str, 
        token_data: Dict[str, Any], 
        user_id: Optional[str] = None
    ) -> bool:
        """トークンデータを保存
        
        Args:
            server_url: MCPサーバーのURL
            token_data: トークンデータ
            user_id: ユーザーID
            
        Returns:
            bool: 保存成功の場合True
        """
        try:
            file_path = self._get_token_file_path(server_url, user_id)
            
            # 暗号化
            encrypted_data = self.crypto.encrypt_token(token_data)
            
            # ファイルに保存
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
            
            # ファイルのパーミッションを制限
            if os.name != 'nt':  # Windows以外
                os.chmod(file_path, 0o600)  # ユーザーのみ読み書き可能
            
            logger.info(f"Token data saved for {server_url} (user: {user_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save token data: {e}")
            return False
    
    def load_token_data(
        self, 
        server_url: str, 
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """トークンデータを読み込み
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID
            
        Returns:
            Optional[Dict[str, Any]]: トークンデータ、存在しない場合はNone
        """
        try:
            file_path = self._get_token_file_path(server_url, user_id)
            
            if not file_path.exists():
                logger.debug(f"No token file found for {server_url} (user: {user_id})")
                return None
            
            # ファイルから読み込み
            with open(file_path, 'r', encoding='utf-8') as f:
                encrypted_data = f.read().strip()
            
            # 復号化
            token_data = self.crypto.decrypt_token(encrypted_data)
            
            logger.debug(f"Token data loaded for {server_url} (user: {user_id})")
            return token_data
            
        except Exception as e:
            logger.error(f"Failed to load token data: {e}")
            return None
    
    def save_client_data(
        self, 
        server_url: str, 
        client_data: Dict[str, Any], 
        user_id: Optional[str] = None
    ) -> bool:
        """クライアント認証情報を保存
        
        Args:
            server_url: MCPサーバーのURL
            client_data: クライアント認証情報
            user_id: ユーザーID
            
        Returns:
            bool: 保存成功の場合True
        """
        try:
            file_path = self._get_client_file_path(server_url, user_id)
            
            # 暗号化
            encrypted_data = self.crypto.encrypt_data(client_data)
            
            # ファイルに保存
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
            
            # ファイルのパーミッションを制限
            if os.name != 'nt':  # Windows以外
                os.chmod(file_path, 0o600)  # ユーザーのみ読み書き可能
            
            logger.info(f"Client data saved for {server_url} (user: {user_id})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save client data: {e}")
            return False
    
    def load_client_data(
        self, 
        server_url: str, 
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """クライアント認証情報を読み込み
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID
            
        Returns:
            Optional[Dict[str, Any]]: クライアント認証情報、存在しない場合はNone
        """
        try:
            file_path = self._get_client_file_path(server_url, user_id)
            
            if not file_path.exists():
                logger.debug(f"No client file found for {server_url} (user: {user_id})")
                return None
            
            # ファイルから読み込み
            with open(file_path, 'r', encoding='utf-8') as f:
                encrypted_data = f.read().strip()
            
            # 復号化
            client_data = self.crypto.decrypt_data(encrypted_data)
            
            logger.debug(f"Client data loaded for {server_url} (user: {user_id})")
            return client_data
            
        except Exception as e:
            logger.error(f"Failed to load client data: {e}")
            return None
    
    def delete_token_data(
        self, 
        server_url: str, 
        user_id: Optional[str] = None
    ) -> bool:
        """トークンデータを削除
        
        Args:
            server_url: MCPサーバーのURL
            user_id: ユーザーID
            
        Returns:
            bool: 削除成功の場合True
        """
        try:
            file_path = self._get_token_file_path(server_url, user_id)
            
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Token data deleted for {server_url} (user: {user_id})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete token data: {e}")
            return False
    
    def delete_client_data(
        self, 
        server_url: str, 
        user_id: Optional[str] = None
    ) -> bool:
        """クライアント認証情報を削除
        
        Args:
            server_url: MCPサーバーのURL  
            user_id: ユーザーID
            
        Returns:
            bool: 削除成功の場合True
        """
        try:
            file_path = self._get_client_file_path(server_url, user_id)
            
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Client data deleted for {server_url} (user: {user_id})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete client data: {e}")
            return False
    
    def list_stored_servers(self, user_id: Optional[str] = None) -> list[str]:
        """保存されているサーバーのリストを取得
        
        Args:
            user_id: ユーザーID
            
        Returns:
            list[str]: サーバーURLのリスト
        """
        user_part = user_id if user_id else 'default'
        suffix = f"_{user_part}_tokens.enc"
        
        servers = []
        
        try:
            for file_path in self.tokens_dir.glob(f"*{suffix}"):
                # ファイル名からサーバー名を復元（不完全だが参考用）
                server_name = file_path.stem.replace(f"_{user_part}_tokens", "")
                servers.append(server_name)
        
        except Exception as e:
            logger.error(f"Failed to list stored servers: {e}")
        
        return servers
    
    def cleanup_old_files(self, max_age_days: int = 30) -> int:
        """古いファイルをクリーンアップ
        
        Args:
            max_age_days: 保持期間（日）
            
        Returns:
            int: 削除されたファイル数
        """
        import time
        
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        deleted_count = 0
        
        try:
            for directory in [self.tokens_dir, self.clients_dir]:
                for file_path in directory.glob("*.enc"):
                    if file_path.stat().st_mtime < cutoff_time:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old file: {file_path.name}")
        
        except Exception as e:
            logger.error(f"Failed to cleanup old files: {e}")
        
        return deleted_count