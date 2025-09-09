"""
Google OAuth2.0認証フローの実装
MCP ADAツール用のユーザー認証を処理
"""
import os
import json
import logging
import webbrowser
from typing import Optional
from pathlib import Path
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

class GoogleAuthManager:
    """Google OAuth2.0認証を管理するクラス"""
    
    def __init__(self, user_id: str = None):
        self.client_secrets_file = None
        
        # ユーザー固有のファイル名
        if user_id:
            self.credentials_file = f"auth_storage/google_auth/google_credentials_{user_id}.json"
        else:
            # 後方互換性のためのデフォルト
            self.credentials_file = "auth_storage/google_auth/google_credentials.json"
            
        self.scopes = [
            'openid',
            'https://www.googleapis.com/auth/adwords',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ]
        self._setup_client_secrets()
    
    def _setup_client_secrets(self):
        """クライアントシークレットファイルの設定"""
        # 環境変数からクライアントシークレットのパスを取得
        self.client_secrets_file = os.getenv('GOOGLE_OAUTH_CLIENT_SECRETS')
        
        # 環境変数から直接認証情報を取得する方法も追加
        client_id = os.getenv('GOOGLE_OAUTH_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET')
        
        if client_id and client_secret:
            # 環境変数から動的にクライアントシークレットを作成
            self._create_client_secrets_from_env(client_id, client_secret)
        elif not self.client_secrets_file or not os.path.exists(self.client_secrets_file):
            # デフォルトのパスを設定
            default_path = "auth_storage/google_auth/client_secrets.json"
            if os.path.exists(default_path):
                self.client_secrets_file = default_path
            else:
                logging.warning("Google OAuth client secrets file not found")
                # デフォルトの設定ファイル作成を促す
                self._create_default_client_secrets()
    
    def _create_default_client_secrets(self):
        """デフォルトのクライアントシークレット設定ファイルを作成"""
        default_secrets = {
            "installed": {
                "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
                "project_id": "your-project-id",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": "YOUR_CLIENT_SECRET",
                "redirect_uris": ["http://localhost:8080"]
            }
        }
        
        default_path = "auth_storage/google_auth/client_secrets.json"
        if not os.path.exists(default_path):
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(default_path), exist_ok=True)
            with open(default_path, 'w') as f:
                json.dump(default_secrets, f, indent=2)
            
            print(f"""
Google OAuth設定ファイルが作成されました: {default_path}
以下の手順で設定を完了してください:

1. Google Cloud Consoleにアクセス: https://console.cloud.google.com
2. プロジェクトを作成または選択
3. APIとサービス > 認証情報 に移動
4. OAuth 2.0 クライアントIDを作成 (デスクトップアプリケーション)
5. クライアントIDとシークレットを{default_path}に記入
6. 環境変数を設定: export GOOGLE_OAUTH_CLIENT_SECRETS="{os.path.abspath(os.path.join(os.getcwd(), default_path))}"
            """)
        
        self.client_secrets_file = default_path
    
    def _create_client_secrets_from_env(self, client_id: str, client_secret: str):
        """環境変数からクライアントシークレットファイルを動的作成"""
        redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8080')
        
        secrets = {
            "installed": {
                "client_id": client_id,
                "project_id": os.getenv('GOOGLE_CLOUD_PROJECT', 'default-project'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri]
            }
        }
        
        temp_secrets_path = "/tmp/google_oauth_secrets.json"
        with open(temp_secrets_path, 'w') as f:
            json.dump(secrets, f, indent=2)
        
        self.client_secrets_file = temp_secrets_path
        logging.info(f"Created temporary client secrets file: {temp_secrets_path}")
    
    def get_access_token(self, force_refresh=False) -> Optional[str]:
        """アクセストークンを取得"""
        try:
            # 既存の認証情報を確認
            credentials = self._load_credentials()
            
            if credentials and credentials.valid and not force_refresh:
                logging.info("Using existing valid credentials")
                return credentials.token
            
            # 認証情報が無効または期限切れの場合、リフレッシュを試行
            if credentials and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    self._save_credentials(credentials)
                    logging.info("Refreshed existing credentials")
                    return credentials.token
                except Exception as e:
                    logging.warning(f"Failed to refresh credentials: {e}")
            
            # 新しい認証フローを開始
            logging.info("Starting new OAuth flow")
            credentials = self._run_oauth_flow()
            
            if credentials:
                self._save_credentials(credentials)
                return credentials.token
            
            return None
            
        except Exception as e:
            logging.error(f"Failed to get access token: {e}")
            return None
    
    def check_auth_status(self) -> tuple[bool, Optional[dict]]:
        """認証状態のみをチェック（認証フローは開始しない）"""
        try:
            credentials = self._load_credentials()
            if not credentials:
                return False, None
            
            # 認証情報が有効かチェック
            if credentials.valid:
                try:
                    from googleapiclient.discovery import build
                    service = build('oauth2', 'v2', credentials=credentials)
                    user_info = service.userinfo().get().execute()
                    
                    return True, {
                        "id": user_info.get("id"),
                        "email": user_info.get("email"),
                        "name": user_info.get("name", user_info.get("email", "Unknown"))
                    }
                except Exception as e:
                    logging.warning(f"Failed to get user info: {e}")
                    return True, {
                        "id": "unknown",
                        "email": "unknown@example.com", 
                        "name": "認証済みユーザー"
                    }
            
            # 認証情報があるがrefreshが必要な場合
            if credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    self._save_credentials(credentials)
                    
                    from googleapiclient.discovery import build
                    service = build('oauth2', 'v2', credentials=credentials)
                    user_info = service.userinfo().get().execute()
                    
                    return True, {
                        "id": user_info.get("id"),
                        "email": user_info.get("email"),
                        "name": user_info.get("name", user_info.get("email", "Unknown"))
                    }
                except Exception as e:
                    logging.warning(f"Failed to refresh credentials: {e}")
                    return False, None
            
            return False, None
            
        except Exception as e:
            logging.error(f"Failed to check auth status: {e}")
            return False, None

    def get_id_token(self, force_refresh=False) -> Optional[str]:
        """IDトークンを取得（MCP ADAサーバー用）"""
        try:
            # 既存の認証情報を確認
            credentials = self._load_credentials()
            
            if credentials and credentials.valid and not force_refresh:
                # Google OAuth2.0ライブラリではIDトークンは_id_tokenプライベート属性に保存される
                if hasattr(credentials, '_id_token') and credentials._id_token:
                    logging.info("Using existing ID token")
                    return credentials._id_token
                # 代替手段: 新しいIDトークンを要求するAPI呼び出し
                return self._request_id_token(credentials)
            
            # 認証情報が無効または期限切れの場合、リフレッシュを試行
            if credentials and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    self._save_credentials(credentials)
                    if hasattr(credentials, '_id_token') and credentials._id_token:
                        logging.info("Refreshed credentials with ID token")
                        return credentials._id_token
                    return self._request_id_token(credentials)
                except Exception as e:
                    logging.warning(f"Failed to refresh credentials: {e}")
            
            # 新しい認証フローを開始
            logging.info("Starting new OAuth flow for ID token")
            credentials = self._run_oauth_flow()
            
            if credentials:
                if hasattr(credentials, '_id_token') and credentials._id_token:
                    self._save_credentials(credentials)
                    return credentials._id_token
                return self._request_id_token(credentials)
            
            logging.warning("No ID token received from OAuth flow")
            return None
            
        except Exception as e:
            logging.error(f"Failed to get ID token: {e}")
            return None
    
    def _request_id_token(self, credentials: Credentials) -> Optional[str]:
        """既存の認証情報からIDトークンを要求"""
        try:
            import requests
            
            # Google OAuth2.0 token endpointにIDトークンを要求
            token_request_data = {
                'grant_type': 'refresh_token',
                'refresh_token': credentials.refresh_token,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scope': 'openid'
            }
            
            response = requests.post(
                'https://oauth2.googleapis.com/token',
                data=token_request_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            if response.status_code == 200:
                token_data = response.json()
                if 'id_token' in token_data:
                    logging.info("Successfully requested ID token")
                    return token_data['id_token']
            
            logging.warning(f"Failed to get ID token from token endpoint: {response.status_code}")
            return None
            
        except Exception as e:
            logging.error(f"Failed to request ID token: {e}")
            return None
    
    def _load_credentials(self) -> Optional[Credentials]:
        """保存された認証情報を読み込み"""
        if os.path.exists(self.credentials_file):
            try:
                return Credentials.from_authorized_user_file(self.credentials_file, self.scopes)
            except Exception as e:
                logging.warning(f"Failed to load credentials: {e}")
        return None
    
    def _save_credentials(self, credentials: Credentials):
        """認証情報を保存"""
        try:
            with open(self.credentials_file, 'w') as f:
                f.write(credentials.to_json())
            logging.info(f"Credentials saved to {self.credentials_file}")
            
            # デバッグ: credentialsオブジェクトの内容を確認
            logging.debug(f"Credentials attributes: {dir(credentials)}")
            if hasattr(credentials, '_id_token'):
                logging.debug(f"ID token available: {credentials._id_token is not None}")
            
        except Exception as e:
            logging.error(f"Failed to save credentials: {e}")
    
    def _run_oauth_flow(self) -> Optional[Credentials]:
        """OAuth認証フローを実行"""
        if not self.client_secrets_file or not os.path.exists(self.client_secrets_file):
            logging.error("Client secrets file not found. Please set up OAuth credentials first.")
            return None
        
        try:
            # OAuth フローを設定
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes
            )
            flow.redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8080')
            
            # 認証URLを生成（IDトークンも要求）
            auth_url, _ = flow.authorization_url(
                prompt='consent',
                access_type='offline',
                include_granted_scopes='true'
            )
            
            print(f"\nGoogle認証が必要です。以下のURLをブラウザで開いてください:")
            print(f"{auth_url}\n")
            
            # ブラウザを自動で開く
            try:
                webbrowser.open(auth_url)
            except:
                pass
            
            # 認証コードの入力を求める
            auth_code = input("認証後に表示される認証コードを入力してください: ").strip()
            
            # アクセストークンとIDトークンを取得
            flow.fetch_token(code=auth_code)
            
            logging.info("OAuth flow completed successfully")
            return flow.credentials
            
        except Exception as e:
            logging.error(f"OAuth flow failed: {e}")
            return None
    
    def process_authorization_code(self, auth_code: str) -> Optional[Credentials]:
        """認証コードからトークンを取得（Webサーバー用）"""
        try:
            if not self.client_secrets_file or not os.path.exists(self.client_secrets_file):
                logging.error("Client secrets file not found")
                return None
            
            # OAuth フローを設定
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=self.scopes
            )
            flow.redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')
            
            # 認証コードを使ってトークンを取得
            flow.fetch_token(code=auth_code)
            
            # 認証情報を保存
            self._save_credentials(flow.credentials)
            
            logging.info("Authorization code processed successfully")
            return flow.credentials
            
        except Exception as e:
            logging.error(f"Failed to process authorization code: {e}")
            return None
    
    def revoke_credentials(self):
        """認証情報を削除"""
        if os.path.exists(self.credentials_file):
            os.remove(self.credentials_file)
            logging.info("Credentials revoked")

# ユーザー単位のインスタンス管理
_auth_managers = {}

def get_auth_manager(user_id: str = None) -> GoogleAuthManager:
    """認証マネージャーのユーザー単位インスタンスを取得"""
    global _auth_managers
    
    # user_idがない場合はデフォルト（後方互換性）
    key = user_id or "default"
    
    if key not in _auth_managers:
        _auth_managers[key] = GoogleAuthManager(user_id)
    
    return _auth_managers[key]

def get_google_access_token(user_id: str = None, force_refresh=False) -> Optional[str]:
    """Google アクセストークンを取得する便利関数（ユーザー単位）"""
    return get_auth_manager(user_id).get_access_token(force_refresh)

def get_google_id_token(user_id: str = None, force_refresh=False) -> Optional[str]:
    """Google IDトークンを取得する便利関数（MCP ADA用、ユーザー単位）"""
    return get_auth_manager(user_id).get_id_token(force_refresh)