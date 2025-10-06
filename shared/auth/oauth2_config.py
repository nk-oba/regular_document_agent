"""
OAuth2設定管理
環境変数や設定ファイルからOAuth2プロバイダーの設定を読み込み
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path


class OAuth2Config:
    """OAuth2設定管理クラス"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Args:
            config_file: 設定ファイルのパス（オプション）
        """
        self.config_file = config_file or "oauth2_config.json"
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """設定を読み込み"""
        config = {
            "default_provider": "generic",
            "providers": {
                "generic": {
                    "token_uri": "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token",
                    "authorization_uri": "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize"
                }
            }
        }
        
        # 環境変数から設定を読み込み
        config["default_provider"] = os.getenv("OAUTH2_PROVIDER", config["default_provider"])
        
        # 設定ファイルが存在する場合は読み込み
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    config.update(file_config)
                logging.info(f"OAuth2 config loaded from {self.config_file}")
            except Exception as e:
                logging.warning(f"Failed to load OAuth2 config file: {e}")
        
        return config
    
    def get_provider_config(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """指定されたプロバイダーの設定を取得"""
        provider = provider or self._config["default_provider"]
        return self._config["providers"].get(provider, {})
    
    def get_token_uri(self, provider: Optional[str] = None) -> str:
        """トークンエンドポイントのURIを取得"""
        provider_config = self.get_provider_config(provider)
        return provider_config.get("token_uri", "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token")
    
    def get_authorization_uri(self, provider: Optional[str] = None) -> str:
        """認証エンドポイントのURIを取得"""
        provider_config = self.get_provider_config(provider)
        return provider_config.get("authorization_uri", "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize")
    
    def get_default_provider(self) -> str:
        """デフォルトプロバイダーを取得"""
        return self._config["default_provider"]
    
    def add_provider(self, provider_name: str, config: Dict[str, Any]):
        """新しいプロバイダーを追加"""
        self._config["providers"][provider_name] = config
        self._save_config()
    
    def _save_config(self):
        """設定をファイルに保存"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logging.info(f"OAuth2 config saved to {self.config_file}")
        except Exception as e:
            logging.error(f"Failed to save OAuth2 config: {e}")


# グローバル設定インスタンス
_oauth2_config = None

def get_oauth2_config() -> OAuth2Config:
    """OAuth2設定インスタンスを取得"""
    global _oauth2_config
    if _oauth2_config is None:
        _oauth2_config = OAuth2Config()
    return _oauth2_config


# 便利な関数
def get_token_uri(provider: Optional[str] = None) -> str:
    """トークンエンドポイントのURIを取得"""
    return get_oauth2_config().get_token_uri(provider)

def get_authorization_uri(provider: Optional[str] = None) -> str:
    """認証エンドポイントのURIを取得"""
    return get_oauth2_config().get_authorization_uri(provider)

def get_default_provider() -> str:
    """デフォルトプロバイダーを取得"""
    return get_oauth2_config().get_default_provider()
