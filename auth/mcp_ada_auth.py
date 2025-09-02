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
from urllib.parse import urlencode, parse_qs, urlparse
import requests

class MCPADAAuthManager:
    """MCP ADA サーバー専用のOAuth 2.0認証マネージャー"""
    
    def __init__(self):
        self.authorization_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize"
        self.token_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token"
        self.registration_endpoint = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/register"
        self.credentials_file = "mcp_ada_credentials.json"
        self.client_credentials_file = "mcp_ada_client.json"
        self.scopes = ["mcp:reports", "mcp:properties"]
        self.redirect_uri = "http://localhost:8080"
        self.client_id = None
        self.client_secret = None
    
    def get_access_token(self, force_refresh=False) -> Optional[str]:
        """MCP ADA用アクセストークンを取得"""
        try:
            # クライアント情報を確保
            if not self._ensure_client_registered():
                logging.error("Failed to register or load client credentials")
                return None
            
            # 既存の認証情報を確認
            credentials = self._load_credentials()
            
            if credentials and self._is_token_valid(credentials) and not force_refresh:
                logging.info("Using existing valid MCP ADA token")
                return credentials.get('access_token')
            
            # リフレッシュトークンでの更新を試行
            if credentials and credentials.get('refresh_token'):
                try:
                    new_credentials = self._refresh_token(credentials['refresh_token'])
                    if new_credentials:
                        self._save_credentials(new_credentials)
                        logging.info("Refreshed MCP ADA token")
                        return new_credentials.get('access_token')
                except Exception as e:
                    logging.warning(f"Failed to refresh MCP ADA token: {e}")
            
            # 新しい認証フローを開始
            logging.info("Starting new MCP ADA OAuth flow")
            credentials = self._run_oauth_flow()
            
            if credentials:
                self._save_credentials(credentials)
                return credentials.get('access_token')
            
            return None
            
        except Exception as e:
            logging.error(f"Failed to get MCP ADA access token: {e}")
            return None
    
    def _load_credentials(self) -> Optional[dict]:
        """保存された認証情報を読み込み"""
        if os.path.exists(self.credentials_file):
            try:
                with open(self.credentials_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load MCP ADA credentials: {e}")
        return None
    
    def _save_credentials(self, credentials: dict):
        """認証情報を保存"""
        try:
            with open(self.credentials_file, 'w') as f:
                json.dump(credentials, f, indent=2)
            logging.info(f"MCP ADA credentials saved to {self.credentials_file}")
        except Exception as e:
            logging.error(f"Failed to save MCP ADA credentials: {e}")
    
    def _is_token_valid(self, credentials: dict) -> bool:
        """トークンの有効性を確認"""
        if not credentials.get('access_token'):
            return False
        
        # expires_at が設定されている場合は期限をチェック
        if 'expires_at' in credentials:
            import time
            return time.time() < credentials['expires_at']
        
        return True
    
    def _generate_pkce_challenge(self):
        """PKCE用のcode_verifierとcode_challengeを生成"""
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        return code_verifier, code_challenge
    
    def _run_oauth_flow(self) -> Optional[dict]:
        """MCP ADA OAuth認証フローを実行"""
        try:
            # PKCE パラメータを生成
            code_verifier, code_challenge = self._generate_pkce_challenge()
            state = secrets.token_urlsafe(32)
            
            # 認証URLを構築
            auth_params = {
                'response_type': 'code',
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'scope': ' '.join(self.scopes),
                'state': state,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256'
            }
            
            auth_url = f"{self.authorization_endpoint}?{urlencode(auth_params)}"
            
            print(f"\nMCP ADA認証が必要です。以下のURLをブラウザで開いてください:")
            print(f"{auth_url}\n")
            
            # ブラウザを自動で開く
            try:
                webbrowser.open(auth_url)
            except:
                pass
            
            # 認証コードの入力を求める
            auth_code = input("認証後に表示される認証コードを入力してください: ").strip()
            
            # URLエンコードされた認証コードをデコード
            from urllib.parse import unquote
            auth_code = unquote(auth_code)
            
            # アクセストークンを取得
            return self._exchange_code_for_token(auth_code, code_verifier)
            
        except Exception as e:
            logging.error(f"MCP ADA OAuth flow failed: {e}")
            return None
    
    def _exchange_code_for_token(self, auth_code: str, code_verifier: str) -> Optional[dict]:
        """認証コードをアクセストークンに交換"""
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
                
                logging.info("Successfully obtained MCP ADA access token")
                return token_response
            else:
                logging.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return None
            
        except Exception as e:
            logging.error(f"Failed to exchange code for token: {e}")
            return None
    
    def _refresh_token(self, refresh_token: str) -> Optional[dict]:
        """リフレッシュトークンを使用してアクセストークンを更新"""
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
            with open(self.client_credentials_file, 'w') as f:
                json.dump(client_info, f, indent=2)
            logging.info(f"Client credentials saved to {self.client_credentials_file}")
        except Exception as e:
            logging.error(f"Failed to save client credentials: {e}")
    
    def _register_client(self) -> bool:
        """動的クライアント登録を実行"""
        try:
            registration_data = {
                "client_name": "MCP ADA Client",
                "redirect_uris": [self.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(self.scopes),
                "token_endpoint_auth_method": "none"  # PKCE使用のためクライアントシークレット不要
            }
            
            response = requests.post(
                self.registration_endpoint,
                json=registration_data,
                headers={'Content-Type': 'application/json'}
            )
            
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
                return False
                
        except Exception as e:
            logging.error(f"Failed to register client: {e}")
            return False
    
    def revoke_credentials(self):
        """認証情報を削除"""
        if os.path.exists(self.credentials_file):
            os.remove(self.credentials_file)
            logging.info("MCP ADA credentials revoked")
        
        if os.path.exists(self.client_credentials_file):
            os.remove(self.client_credentials_file)
            logging.info("MCP ADA client credentials revoked")

# グローバルインスタンス
_mcp_ada_auth_manager = None

def get_mcp_ada_auth_manager() -> MCPADAAuthManager:
    """MCP ADA認証マネージャーのシングルトンインスタンスを取得"""
    global _mcp_ada_auth_manager
    if _mcp_ada_auth_manager is None:
        _mcp_ada_auth_manager = MCPADAAuthManager()
    return _mcp_ada_auth_manager

def get_mcp_ada_access_token(force_refresh=False) -> Optional[str]:
    """MCP ADA アクセストークンを取得する便利関数"""
    return get_mcp_ada_auth_manager().get_access_token(force_refresh)