import os
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from middleware import auth_middleware
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import json
import asyncio
from typing import List, Optional
import logging
import re
from fastapi import Request

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

# MCP ADA認証コールバック用のHTMLエンドポイント
@app.get("/static/mcp_ada_callback.html", response_class=HTMLResponse)
async def mcp_ada_callback_html():
    """MCP ADA認証コールバック用のHTMLページ"""
    try:
        with open("mcp_ada_callback.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>MCP ADA Callback page not found</h1>", status_code=404)

# 静的ファイルの設定（その他の静的ファイル用）
app.mount("/static", StaticFiles(directory="."), name="static")

# CORS設定を最後に適用してget_fast_api_appの設定を上書き
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

# ユーザーIDを取得するヘルパー関数
def get_current_user_id() -> Optional[str]:
    """現在認証されているユーザーのIDを取得"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        is_authenticated, user_info = auth_manager.check_auth_status()
        
        if is_authenticated and user_info:
            # ユーザーIDとしてemailを使用（一意性を保証）
            return user_info.get("email", user_info.get("id"))
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get current user ID: {e}")
        return None

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
        
        # 初回認証時はデフォルトマネージャーを使用（後でユーザー固有に移行）
        auth_manager = get_auth_manager()
        
        # 認証コードを使ってトークンを取得
        credentials = auth_manager.process_authorization_code(code)
        
        if credentials:
            # 認証成功後、ユーザー情報を取得してユーザー固有の認証情報に移行
            try:
                is_authenticated, user_info = auth_manager.check_auth_status()
                if is_authenticated and user_info:
                    user_id = user_info.get("email", user_info.get("id"))
                    if user_id:
                        # ユーザー固有の認証マネージャーを取得
                        user_auth_manager = get_auth_manager(user_id)
                        # 認証情報をユーザー固有のファイルに保存
                        user_auth_manager._save_credentials(credentials)
                        logger.info(f"Credentials saved for user: {user_id}")
            except Exception as e:
                logger.warning(f"Failed to migrate credentials to user-specific file: {e}")
                # エラーが発生してもメインの認証フローは継続
        
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
    """現在の認証ステータスを確認（認証フローは開始しない）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        
        # ユーザー固有の認証マネージャーを取得
        if user_id:
            auth_manager = get_auth_manager(user_id)
        else:
            # 最初の認証時はデフォルトマネージャーもチェック
            auth_manager = get_auth_manager()
        
        # 認証状態のみをチェック（認証フローは開始しない）
        is_authenticated, user_info = auth_manager.check_auth_status()
        
        if is_authenticated and user_info:
            return {
                "authenticated": True,
                "user": user_info
            }
        
        return {"authenticated": False}
        
    except Exception as e:
        logger.error(f"Auth status check error: {e}")
        return {"authenticated": False, "error": str(e)}

# Google OAuth2.0ログアウトエンドポイント
@app.post("/auth/logout")
async def logout():
    """認証情報をクリア（ユーザー単位）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        
        if user_id:
            # ユーザー固有の認証マネージャーを取得
            auth_manager = get_auth_manager(user_id)
            auth_manager.revoke_credentials()
            return {"success": True, "message": f"Logged out successfully for user {user_id}"}
        else:
            # デフォルトマネージャーの認証情報もクリア
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
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        
        # ユーザー固有の認証マネージャーを取得
        if user_id:
            auth_manager = get_auth_manager(user_id)
        else:
            # 最初の認証時はデフォルトマネージャーを使用
            auth_manager = get_auth_manager()
        
        # 既存の認証情報をチェック（認証フローは開始しない）
        is_authenticated, user_info = auth_manager.check_auth_status()
        if is_authenticated:
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

# MCP ADA認証ステータス確認エンドポイント
@app.get("/auth/mcp-ada/status")
async def mcp_ada_auth_status():
    """MCP ADA認証ステータスを確認（ユーザー単位）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        if not user_id:
            return {"authenticated": False, "service": "MCP ADA", "error": "User not authenticated"}
        
        # ユーザー固有の認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager(user_id)
        
        # 既存の認証情報をチェック（認証フローは開始しない）
        credentials = auth_manager._load_credentials()
        if credentials and auth_manager._is_token_valid(credentials):
            return {
                "authenticated": True,
                "service": "MCP ADA",
                "scopes": auth_manager.scopes,
                "user_id": user_id
            }
            
        return {"authenticated": False, "service": "MCP ADA", "user_id": user_id}
        
    except Exception as e:
        logger.error(f"MCP ADA auth status check error: {e}")
        return {"authenticated": False, "service": "MCP ADA", "error": str(e)}

# MCP ADA認証開始エンドポイント
@app.get("/auth/mcp-ada/start")
async def start_mcp_ada_oauth():
    """MCP ADA OAuth2.0認証を開始（ユーザー単位）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        if not user_id:
            return {
                "success": False,
                "message": "User not authenticated. Please login with Google first.",
                "authenticated": False
            }
        
        # ユーザー固有の認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager(user_id)
        
        # 既存の認証情報をチェック（認証フローは開始しない）
        credentials = auth_manager._load_credentials()
        if credentials and auth_manager._is_token_valid(credentials):
            return {
                "success": True,
                "message": f"Already authenticated with MCP ADA for user {user_id}",
                "authenticated": True,
                "user_id": user_id
            }
        
        # クライアント情報を確保
        if not auth_manager._ensure_client_registered():
            return {
                "success": False,
                "message": "Failed to register MCP ADA client",
                "authenticated": False
            }
        
        # 認証URLを生成してフロントエンドに返す
        try:
            auth_url, state, code_verifier = auth_manager.generate_auth_url()
            
            return {
                "success": True,
                "auth_url": auth_url,
                "state": state,
                "message": "Please complete authentication in the browser",
                "authenticated": False
            }
        except ValueError as e:
            logger.error(f"MCP ADA auth URL generation failed: {e}")
            return {
                "success": False,
                "message": f"Failed to generate auth URL: {str(e)}",
                "authenticated": False
            }
        
    except Exception as e:
        logger.error(f"MCP ADA OAuth start error: {e}")
        return {"error": f"Failed to start MCP ADA authentication: {str(e)}"}

# MCP ADA認証コールバックエンドポイント
@app.post("/auth/mcp-ada/callback")
async def mcp_ada_callback(request: dict):
    """MCP ADA認証コールバック処理（ユーザー単位）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        if not user_id:
            return {
                "success": False,
                "message": "User not authenticated. Please login with Google first.",
                "authenticated": False
            }
        
        # ユーザー固有の認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager(user_id)
        
        # 認証コードを取得
        auth_code = request.get('code')
        state = request.get('state')
        
        if not auth_code:
            return {
                "success": False,
                "message": "Authorization code not provided",
                "authenticated": False
            }
        
        # 認証コードを処理してトークンを取得
        credentials = auth_manager.process_auth_code(auth_code, state)
        
        if credentials:
            return {
                "success": True,
                "message": "MCP ADA authentication completed successfully",
                "authenticated": True
            }
        else:
            return {
                "success": False,
                "message": "Failed to process authorization code",
                "authenticated": False
            }
        
    except Exception as e:
        logger.error(f"MCP ADA callback error: {e}")
        return {"error": f"Failed to process MCP ADA callback: {str(e)}"}

# MCP ADA認証ログアウトエンドポイント
@app.post("/auth/mcp-ada/logout")
async def mcp_ada_logout():
    """MCP ADA認証情報をクリア（ユーザー単位）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # 現在のユーザーIDを取得
        user_id = get_current_user_id()
        if not user_id:
            return {"success": False, "error": "User not authenticated"}
        
        # ユーザー固有の認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager(user_id)
        auth_manager.revoke_credentials()
        
        return {
            "success": True, 
            "message": f"MCP ADA credentials cleared successfully for user {user_id}",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"MCP ADA logout error: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    logger.info("Starting application...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        traceback.print_exc()