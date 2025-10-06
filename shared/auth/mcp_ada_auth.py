"""
MCP ADA サーバー専用の認証システム
独自のOAuth 2.0認可サーバーを使用
"""
import os
import json
import logging
import webbrowser
import secrets
import hashlib
import base64
from typing import Optional
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse
import requests

class MCPADAAuthManager:
    """
    MCP ADA サーバー専用の認証マネージャー
    OAuth 2.0 + PKCE を使用した認証フロー
    """
    
    def __init__(self, user_id: str = None):
        self.authorization_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize"
        self.token_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token"
        self.registration_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/register"
        
        # ユーザー固有のファイル名
        if user_id:
            self.credentials_file = f"auth_storage/mcp_ada_auth/mcp_ada_credentials_{user_id}.json"
            self.client_credentials_file = f"auth_storage/mcp_ada_auth/mcp_ada_client_{user_id}.json"
        else:
            # デフォルトのファイル名を設定
            self.credentials_file = "auth_storage/mcp_ada_auth/mcp_ada_credentials_default.json"
            self.client_credentials_file = "auth_storage/mcp_ada_auth/mcp_ada_client_default.json"
        self.scopes = ["mcp:reports", "mcp:properties"]
        
        # 環境変数でリダイレクトURIを設定
        redirect_uri = os.getenv("MCP_ADA_REDIRECT_URI")
        if not redirect_uri:
            redirect_uri = "http://localhost:8000/static/mcp_ada_callback.html"
            logging.warning("MCP_ADA_REDIRECT_URI not set. Using localhost (development only)")
        self.redirect_uri = redirect_uri
        
        self.client_id = None
        self.client_secret = None
    
    def get_access_token(self, force_refresh=False) -> Optional[str]:
        """アクセストークンを取得"""
        try:
            credentials = self._load_credentials()
            if not credentials:
                return None
            
            # トークンの有効性をチェック
            if not force_refresh and self._is_token_valid(credentials):
                return credentials.get('access_token')
            
            # リフレッシュトークンを使用して更新
            if credentials.get('refresh_token'):
                new_credentials = self._refresh_token(credentials['refresh_token'])
                if new_credentials:
                    self._save_credentials(new_credentials)
                    return new_credentials.get('access_token')
            
            return None
        except Exception as e:
            logging.error(f"Failed to get access token: {e}")
            return None
    
    def _is_token_valid(self, credentials: dict) -> bool:
        """トークンの有効性をチェック"""
        if not credentials.get('access_token'):
            return False
        
        # expires_at が設定されている場合はチェック
        if 'expires_at' in credentials:
            import time
            return time.time() < credentials['expires_at']
        
        return True
    
    def _load_credentials(self) -> Optional[dict]:
        """認証情報を読み込み"""
        if os.path.exists(self.credentials_file):
            try:
                with open(self.credentials_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load credentials: {e}")
        return None
    
    def _save_credentials(self, credentials: dict):
        """認証情報を保存"""
        try:
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(self.credentials_file), exist_ok=True)
            
            with open(self.credentials_file, 'w') as f:
                json.dump(credentials, f, indent=2)
            
            # ファイルのパーミッションを制限 (セキュリティ強化)
            os.chmod(self.credentials_file, 0o600)
            
            logging.info(f"Credentials saved to {self.credentials_file}")
        except Exception as e:
            logging.error(f"Failed to save credentials: {e}")
            raise
    
    def generate_auth_url(self) -> tuple:
        """認証URLを生成"""
        try:
            # PKCE用のcode_verifierとcode_challengeを生成
            code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
            code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode('utf-8')).digest()
            ).decode('utf-8').rstrip('=')
            
            # stateパラメータを生成
            state = secrets.token_urlsafe(32)
            
            # 認証URLを構築
            params = {
                'response_type': 'code',
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'scope': ' '.join(self.scopes),
                'state': state,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256'
            }
            
            auth_url = f"{self.authorization_endpoint}?{urlencode(params)}"
            
            # code_verifierを一時的に保存
            self._save_code_verifier(code_verifier)
            
            return auth_url, state, code_verifier
            
        except Exception as e:
            logging.error(f"Failed to generate auth URL: {e}")
            raise
    
    def _save_code_verifier(self, code_verifier: str):
        """PKCE用のcode_verifierを一時保存"""
        try:
            temp_file = f"{self.credentials_file}.temp"
            with open(temp_file, 'w') as f:
                f.write(code_verifier)
            os.chmod(temp_file, 0o600)
        except Exception as e:
            logging.warning(f"Failed to save code verifier: {e}")
    
    def _load_code_verifier(self) -> Optional[str]:
        """PKCE用のcode_verifierを読み込み"""
        try:
            temp_file = f"{self.credentials_file}.temp"
            if os.path.exists(temp_file):
                with open(temp_file, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logging.warning(f"Failed to load code verifier: {e}")
        return None
    
    def process_auth_code(self, auth_code: str, state: str) -> Optional[dict]:
        """認証コードを処理してトークンを取得"""
        try:
            code_verifier = self._load_code_verifier()
            if not code_verifier:
                logging.error("Code verifier not found")
                return None
            
            # トークンエンドポイントにリクエスト（PKCEのみ、client_secretは不要）
            token_data = {
                'grant_type': 'authorization_code',
                'code': auth_code,
                'redirect_uri': self.redirect_uri,
                'client_id': self.client_id,
                'code_verifier': code_verifier
            }
            
            response = requests.post(
                self.token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                
                # expires_at を計算して追加
                if 'expires_in' in token_response:
                    import time
                    token_response['expires_at'] = time.time() + token_response['expires_in']
                
                # 認証情報を保存
                self._save_credentials(token_response)
                
                # 一時ファイルを削除
                self._cleanup_temp_files()
                
                logging.info("Authentication completed successfully")
                return token_response
            else:
                logging.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Failed to process auth code: {e}")
            return None
    
    def _cleanup_temp_files(self):
        """一時ファイルをクリーンアップ"""
        try:
            temp_file = f"{self.credentials_file}.temp"
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            logging.warning(f"Failed to cleanup temp files: {e}")
    
    def _exchange_code_for_token(self, auth_code: str, code_verifier: str) -> Optional[dict]:
        """認証コードをトークンに交換"""
        try:
            token_data = {
                'grant_type': 'authorization_code',
                'code': auth_code,
                'redirect_uri': self.redirect_uri,
                'client_id': self.client_id,
                'code_verifier': code_verifier
            }
            
            response = requests.post(
                self.token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                
                # expires_at を計算して追加
                if 'expires_in' in token_response:
                    import time
                    token_response['expires_at'] = time.time() + token_response['expires_in']
                
                return token_response
            else:
                logging.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Failed to exchange code for token: {e}")
            return None
    
    def _refresh_token(self, refresh_token: str) -> Optional[dict]:
        """リフレッシュトークンを使用してアクセストークンを更新（PKCEパブリッククライアント）"""
        try:
            token_data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id
            }
            
            response = requests.post(
                self.token_endpoint,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_response = response.json()
                
                # expires_at を計算して追加
                if 'expires_in' in token_response:
                    import time
                    token_response['expires_at'] = time.time() + token_response['expires_in']
                
                return token_response
            else:
                logging.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Failed to refresh token: {e}")
            return None
    
    def _ensure_client_registered(self) -> bool:
        """クライアントが登録されていることを確認"""
        # 既存のクライアント情報を読み込み
        client_info = self._load_client_credentials()
        if client_info and client_info.get('client_id'):
            self.client_id = client_info['client_id']
            self.client_secret = client_info.get('client_secret')
            logging.info(f"Using existing client ID: {self.client_id}")
            return True

        # 新しいクライアントを登録
        return self._register_client()
    
    def _load_client_credentials(self) -> Optional[dict]:
        """クライアント認証情報を読み込み"""
        if os.path.exists(self.client_credentials_file):
            try:
                with open(self.client_credentials_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load client credentials: {e}")
        return None
    
    def _save_client_credentials(self, client_info: dict):
        """クライアント認証情報を保存"""
        try:
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(self.client_credentials_file), exist_ok=True)
            
            with open(self.client_credentials_file, 'w') as f:
                json.dump(client_info, f, indent=2)
            
            # ファイルのパーミッションを制限 (セキュリティ強化)
            os.chmod(self.client_credentials_file, 0o600)
            
            logging.info(f"Client credentials saved to {self.client_credentials_file}")
        except Exception as e:
            logging.error(f"Failed to save client credentials: {e}")
            raise
    
    def _register_client(self) -> bool:
        """動的クライアント登録を実行"""
        try:
            logging.info(f"Registering MCP Ad Analyzer client with endpoint: {self.registration_endpoint}")
            logging.info(f"Redirect URI: {self.redirect_uri}")
            
            registration_data = {
                "client_name": "MCP Ad Analyzer Client",
                "redirect_uris": [self.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(self.scopes),
                "token_endpoint_auth_method": "none"  # PKCEを使用するパブリッククライアント
            }
            
            logging.info(f"Registration data: {registration_data}")
            
            response = requests.post(
                self.registration_endpoint,
                json=registration_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            logging.info(f"Registration response status: {response.status_code}")
            logging.info(f"Registration response headers: {dict(response.headers)}")
            
            if response.status_code == 201:
                client_info = response.json()

                self.client_id = client_info['client_id']
                self.client_secret = client_info.get('client_secret')

                # クライアント情報を保存
                self._save_client_credentials(client_info)

                logging.info(f"Successfully registered client: {self.client_id}")
                return True
            else:
                logging.error(f"Client registration failed: {response.status_code} - {response.text}")
                try:
                    error_data = response.json()
                    logging.error(f"Error details: {error_data}")
                except:
                    logging.error(f"Raw error response: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during client registration: {e}")
            return False
        except Exception as e:
            logging.error(f"Failed to register client: {e}")
            return False
    
    def revoke_credentials(self):
        """認証情報を削除"""
        if os.path.exists(self.credentials_file):
            os.remove(self.credentials_file)
            logging.info("MCP Ad Analyzer credentials revoked")
        
        if os.path.exists(self.client_credentials_file):
            os.remove(self.client_credentials_file)
            logging.info("MCP Ad Analyzer client credentials revoked")

# ユーザー単位のインスタンス管理
_mcp_ada_auth_managers = {}

def get_mcp_ada_auth_manager(user_id: str = None) -> MCPADAAuthManager:
    """ユーザー固有のMCP ADA認証マネージャーを取得"""
    if user_id not in _mcp_ada_auth_managers:
        _mcp_ada_auth_managers[user_id] = MCPADAAuthManager(user_id)
    return _mcp_ada_auth_managers[user_id]