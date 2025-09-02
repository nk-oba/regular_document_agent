import os
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from middleware import auth_middleware
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import json
import asyncio
from typing import List
import logging
import re

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# agent engone parameters
AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
SESSION_DB_URL = "sqlite:///./sessions.db"
ARTIFACT_URL = "gs://dev-datap-agent-bucket"
ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000", 
    "http://localhost:3000", 
    "http://127.0.0.1:3001", 
    "http://localhost:3001",
    "http://127.0.0.1:8000", 
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]
SERVE_WEB_INTERFACE = True

load_dotenv()

# エージェントを安全にインポート
try:
    from agents.document_creating_agent.agent import root_agent
    logger.info("Successfully imported root_agent")
except Exception as e:
    logger.error(f"Failed to import root_agent: {str(e)}")
    import traceback
    traceback.print_exc()
    root_agent = None

try:
    google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if google_creds_path and os.path.exists(google_creds_path.replace("/app/", "/app/")):
        logger.info(f"Using GCS Artifact Service with credentials: {google_creds_path}")
        app: FastAPI = get_fast_api_app(
            agents_dir=AGENT_DIR,
            session_service_uri=SESSION_DB_URL,
            artifact_service_uri=ARTIFACT_URL,  # GCSを使用
            allow_origins=ALLOWED_ORIGINS,
            web=SERVE_WEB_INTERFACE
        )
    else:
        logger.info("Using InMemory Artifact Service (no GCS credentials found)")
        app: FastAPI = get_fast_api_app(
            agents_dir=AGENT_DIR,
            session_service_uri=SESSION_DB_URL,
            # artifact_service_uri=ARTIFACT_URL,  # InMemoryを使用
            allow_origins=ALLOWED_ORIGINS,
            web=SERVE_WEB_INTERFACE
        )
    logger.info("Successfully created FastAPI app")
except Exception as e:
    logger.error(f"Failed to create FastAPI app: {str(e)}")
    import traceback
    traceback.print_exc()
    raise


# 認証ミドルウェアを追加（CORSより前に）
app.middleware("http")(auth_middleware)

# CORS設定を最後に適用してget_fast_api_appの設定を上書き
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

# 手動でOPTIONSリクエストに対応
@app.options("/{path:path}")
async def options_handler():
    return {"message": "OK"}

# Google OAuth2.0コールバックエンドポイント
@app.get("/auth/callback")
async def oauth_callback(code: str = None, error: str = None):
    """Google OAuth2.0認証コールバック"""
    if error:
        return {"error": f"Authentication failed: {error}"}
    
    if not code:
        return {"error": "No authorization code provided"}
    
    try:
        logger.info(f"Processing OAuth callback with code: {code[:20]}...")
        
        # 認証コードをauth moduleに渡して処理
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        
        # 認証コードを使ってトークンを取得
        credentials = auth_manager.process_authorization_code(code)
        
        if credentials:
            logger.info("OAuth credentials successfully obtained")
            # 認証成功後、フロントエンドにリダイレクト
            return RedirectResponse(url="http://localhost:3000", status_code=302)
        else:
            logger.error("Failed to obtain OAuth credentials")
            return {
                "success": False,
                "message": "Failed to process authorization code. Please try again.",
                "token_obtained": False
            }
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"error": f"Authentication processing failed: {str(e)}"}

# Google OAuth2.0認証ステータス確認エンドポイント
@app.get("/auth/status")
async def auth_status():
    """現在の認証ステータスを確認"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        
        # 既存の認証情報をチェック
        existing_token = auth_manager.get_access_token()
        if existing_token:
            # ユーザー情報を取得
            credentials = auth_manager._load_credentials()
            if credentials:
                try:
                    from google.oauth2.credentials import Credentials
                    from googleapiclient.discovery import build
                    
                    # Google User Info APIでユーザー情報を取得
                    service = build('oauth2', 'v2', credentials=credentials)
                    user_info = service.userinfo().get().execute()
                    
                    return {
                        "authenticated": True,
                        "user": {
                            "id": user_info.get("id"),
                            "email": user_info.get("email"),
                            "name": user_info.get("name", user_info.get("email", "Unknown"))
                        }
                    }
                except Exception as e:
                    logger.warning(f"Failed to get user info: {e}")
                    return {
                        "authenticated": True,
                        "user": {
                            "id": "unknown",
                            "email": "unknown@example.com",
                            "name": "認証済みユーザー"
                        }
                    }
            
        return {"authenticated": False}
        
    except Exception as e:
        logger.error(f"Auth status check error: {e}")
        return {"authenticated": False, "error": str(e)}

# Google OAuth2.0ログアウトエンドポイント
@app.post("/auth/logout")
async def logout():
    """認証情報をクリア"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        auth_manager.revoke_credentials()
        
        return {"success": True, "message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return {"success": False, "error": str(e)}

# Google OAuth2.0認証開始エンドポイント
@app.get("/auth/start")
async def start_oauth():
    """Google OAuth2.0認証を開始"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        
        # 既存の認証情報をチェック
        existing_token = auth_manager.get_access_token()
        if existing_token:
            return {
                "success": True,
                "message": "Already authenticated",
                "authenticated": True
            }
        
        # 認証URLを生成（認証フロー開始）
        if not auth_manager.client_secrets_file or not os.path.exists(auth_manager.client_secrets_file):
            return {"error": "OAuth client secrets not configured"}
        
        from google_auth_oauthlib.flow import Flow
        
        flow = Flow.from_client_secrets_file(
            auth_manager.client_secrets_file,
            scopes=auth_manager.scopes
        )
        flow.redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')
        
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        return {
            "success": True,
            "auth_url": auth_url,
            "message": "Please visit the auth_url to complete authentication"
        }
        
    except Exception as e:
        logger.error(f"OAuth start error: {e}")
        return {"error": f"Failed to start authentication: {str(e)}"}

if __name__ == "__main__":
    logger.info("Starting application...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        traceback.print_exc()