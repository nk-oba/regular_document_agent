import os
import asyncio
import time
from contextlib import asynccontextmanager
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from middleware import auth_middleware
from typing import Optional
import logging
import io

# Import new configuration and utilities
from config import AppConfig, LogConfig
from app_utils import generate_adk_user_id
from error_handlers import handle_auth_error, handle_session_error, create_success_response

# ログ設定
logging.basicConfig(
    level=getattr(logging, LogConfig.LEVEL),
    format=LogConfig.FORMAT
)
logger = logging.getLogger(__name__)

# バックグラウンドタスク用のグローバル変数
background_task = None

async def session_cleanup_task():
    """セッションクリーンアップのバックグラウンドタスク"""
    from auth.session_auth import get_session_auth_manager
    from auth.session_sync_manager import get_session_sync_manager
    
    while True:
        try:
            # ログインセッションのクリーンアップ
            session_manager = get_session_auth_manager()
            session_manager.cleanup_expired_sessions()
            
            # 孤立ADKセッションのクリーンアップ
            current_time = int(time.time())
            if current_time % AppConfig.ORPHANED_ADK_CLEANUP_INTERVAL < 60:
                sync_manager = get_session_sync_manager()
                orphaned_count = sync_manager.cleanup_orphaned_adk_sessions()
                if orphaned_count > 0:
                    logger.info(f"Background cleanup: removed {orphaned_count} orphaned ADK sessions")
            
            # 古いアーカイブチャットのクリーンアップ
            if current_time % AppConfig.ARCHIVED_CHAT_CLEANUP_INTERVAL < 60:
                sync_manager = get_session_sync_manager()
                archived_deleted = sync_manager.cleanup_old_archived_chats(AppConfig.ARCHIVED_CHAT_RETENTION_DAYS)
                if archived_deleted > 0:
                    logger.info(f"Background cleanup: removed {archived_deleted} old archived chats")
            
            await asyncio.sleep(AppConfig.SESSION_CLEANUP_INTERVAL)
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
            await asyncio.sleep(AppConfig.SESSION_CLEANUP_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPIアプリのライフスパン管理"""
    global background_task
    
    # 起動時の処理
    logger.info("Starting FastAPI application")
    
    # バックグラウンドタスクを開始
    try:
        background_task = asyncio.create_task(session_cleanup_task())
        logger.info("Successfully started session cleanup task")
    except Exception as e:
        logger.warning(f"Could not start session cleanup: {e}")
    
    yield
    
    # 終了時の処理
    logger.info("Shutting down FastAPI application")
    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            logger.info("Session cleanup task cancelled")

# Configuration is now handled by AppConfig class
# Legacy variables for backward compatibility
AGENT_DIR = AppConfig.AGENT_DIR
SESSION_DB_URL = AppConfig.SESSION_DB_URL
ARTIFACT_URL = AppConfig.ARTIFACT_URL
USE_UNIFIED_SESSION_MANAGEMENT = AppConfig.USE_UNIFIED_SESSION_MANAGEMENT
ALLOWED_ORIGINS = AppConfig.ALLOWED_ORIGINS
SERVE_WEB_INTERFACE = AppConfig.SERVE_WEB_INTERFACE

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
    if AppConfig.is_gcs_enabled():
        logger.info(f"Using GCS Artifact Service with credentials: {AppConfig.GOOGLE_APPLICATION_CREDENTIALS}")
        app: FastAPI = get_fast_api_app(
            agents_dir=AppConfig.AGENT_DIR,
            session_service_uri=AppConfig.SESSION_DB_URL,
            artifact_service_uri=AppConfig.ARTIFACT_URL,  # GCSを使用
            allow_origins=AppConfig.ALLOWED_ORIGINS,
            web=AppConfig.SERVE_WEB_INTERFACE,
            lifespan=lifespan
        )
    else:
        logger.info("Using InMemory Artifact Service (no GCS credentials found)")
        app: FastAPI = get_fast_api_app(
            agents_dir=AppConfig.AGENT_DIR,
            session_service_uri=AppConfig.SESSION_DB_URL,
            # artifact_service_uri=AppConfig.ARTIFACT_URL,  # InMemoryを使用
            allow_origins=AppConfig.ALLOWED_ORIGINS,
            web=AppConfig.SERVE_WEB_INTERFACE,
            lifespan=lifespan
        )
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
    allow_origins=AppConfig.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"CORS allowed origins: {AppConfig.ALLOWED_ORIGINS}")

# 統一されたユーザー識別ヘルパー関数
def get_current_user_id(request: Request = None) -> Optional[str]:
    """現在認証されているユーザーのIDを取得
    
    Args:
        request: FastAPIのRequestオブジェクト（セッション認証用）
                Noneの場合はMCP用の認証情報を使用
    
    Returns:
        ユーザーID（email）またはNone
    """
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        
        # リクエストがある場合はセッションベース認証を優先
        if request is not None:
            from auth.session_auth import get_session_auth_manager
            
            session_manager = get_session_auth_manager()
            user_info = session_manager.get_user_info(request)
            
            if user_info:
                return user_info.get("email", user_info.get("id"))
        
        # フォールバックとしてMCP認証を使用
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        is_authenticated, user_info = auth_manager.check_auth_status()
        
        if is_authenticated and user_info:
            return user_info.get("email", user_info.get("id"))
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get current user ID: {e}")
        return None

def get_current_adk_user_id(request: Request = None) -> str:
    """ADK用の安定したユーザーIDを取得
    
    Args:
        request: FastAPIのRequestオブジェクト
    
    Returns:
        ADK用のユーザーID（16文字のハッシュ）
    """
    try:
        # リクエストがない場合はanonymous
        if not request:
            return "anonymous"
        
        # セッション情報から直接ユーザー情報を取得（最も確実な方法）
        from auth.session_auth import get_session_auth_manager
        
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info and user_info.get("email"):
            # emailをベースにした安定的なuser_id（16文字）
            email = user_info["email"]
            adk_user_id = generate_adk_user_id(email)
            
            # デバッグログ
            logger.debug(f"Generated ADK user ID: {adk_user_id} for email: {email[:5]}...")
            
            return adk_user_id
        
        return "anonymous"
        
    except Exception as e:
        logger.error(f"Failed to get ADK user ID: {e}")
        return "anonymous"

# MCP認証用の互換性維持関数
def get_current_user_id_for_mcp() -> Optional[str]:
    """MCP認証用のユーザーIDを取得（互換性維持）"""
    return get_current_user_id(request=None)

# 手動でOPTIONSリクエストに対応
@app.options("/{path:path}")
async def options_handler():
    return {"message": "OK"}

# ADKユーザーID確認用エンドポイント
@app.get("/auth/adk-user-id")
async def get_adk_user_id_status(request: Request):
    """現在のADKユーザーIDステータスを確認"""
    try:
        adk_user_id = get_current_adk_user_id(request)
        user_email = get_current_user_id(request)
        
        return {
            "adk_user_id": adk_user_id,
            "user_email": user_email,
            "authenticated": adk_user_id != "anonymous",
            "stable_id_generated": len(adk_user_id) == 16 and adk_user_id != "anonymous"
        }
    except Exception as e:
        logger.error(f"Failed to get ADK user ID status: {e}")
        return {"error": str(e)}

# Google OAuth2.0コールバックエンドポイント
@app.get("/auth/callback")
async def oauth_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    """Google OAuth2.0認証コールバック（セッションベース）"""
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
        from auth.session_auth import get_session_auth_manager
        
        # 一時的な認証マネージャーを使用してトークンを取得
        temp_auth_manager = get_auth_manager()
        credentials = temp_auth_manager.process_authorization_code(code)
        
        if credentials:
            # ユーザー情報を取得
            try:
                from googleapiclient.discovery import build
                service = build('oauth2', 'v2', credentials=credentials)
                user_info = service.userinfo().get().execute()
                
                user_data = {
                    "id": user_info.get("id"),
                    "email": user_info.get("email"),
                    "name": user_info.get("name", user_info.get("email", "Unknown"))
                }
                
                # セッション管理方式の選択
                if USE_UNIFIED_SESSION_MANAGEMENT:
                    # 統合セッション管理を使用（フォールバック付き）
                    try:
                        from auth.unified_session_manager import get_unified_session_manager
                        unified_manager = get_unified_session_manager()
                        unified_session = unified_manager.create_unified_session(user_data, credentials)
                        session_id = unified_session["login_session_id"]
                        adk_user_id = unified_session["adk_user_id"]
                        logger.info(f"Using unified session management")
                    except Exception as e:
                        logger.warning(f"Unified session failed, using sync manager: {e}")
                        # フォールバック: 従来のセッション同期管理
                        from auth.session_sync_manager import get_session_sync_manager
                        sync_manager = get_session_sync_manager()
                        session_id, adk_user_id = sync_manager.on_login(user_data, credentials)
                else:
                    # 従来のセッション同期管理を使用
                    from auth.session_sync_manager import get_session_sync_manager
                    sync_manager = get_session_sync_manager()
                    session_id, adk_user_id = sync_manager.on_login(user_data, credentials)
                    logger.info(f"Using sync session management")
                
                # MCP用の従来システムにも保存（ユーザー共通）
                user_id = user_data.get("email", user_data.get("id"))
                if user_id:
                    user_auth_manager = get_auth_manager(user_id)
                    user_auth_manager._save_credentials(credentials)
                    logger.info(f"Credentials saved for MCP user: {user_id}")
                
                logger.info(f"Unified session created - Login: {session_id}, ADK user: {adk_user_id}")
                
                # セッションクッキー付きでリダイレクト
                session_manager = get_session_auth_manager()
                response = RedirectResponse(url=AppConfig.FRONTEND_REDIRECT_URL, status_code=302)
                session_manager.set_session_cookie(response, session_id)
                return response
                
            except Exception as e:
                return handle_auth_error(e, "get user info")
        else:
            logger.error("Failed to obtain OAuth credentials")
            return {
                "success": False,
                "message": "Failed to process authorization code. Please try again.",
                "token_obtained": False
            }
        
    except Exception as e:
        return handle_auth_error(e, "OAuth callback processing", include_traceback=True)

# Google OAuth2.0認証ステータス確認エンドポイント
@app.get("/auth/status")
async def auth_status(request: Request):
    """現在の認証ステータスを確認（セッションベース）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.session_auth import get_session_auth_manager
        
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info:
            return {
                "authenticated": True,
                "user": user_info
            }
        
        return {"authenticated": False}
        
    except Exception as e:
        return handle_auth_error(e, "auth status check")

# Google OAuth2.0ログアウトエンドポイント
@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    """認証情報をクリア（セッションベース）"""
    try:
        from auth.session_auth import get_session_auth_manager
        from auth.session_sync_manager import get_session_sync_manager
        
        session_manager = get_session_auth_manager()
        sync_manager = get_session_sync_manager()
        
        session_id = session_manager.get_session_id_from_request(request)
        
        if session_id:
            # ADKユーザーIDを事前に取得（セッション削除前に）
            adk_user_id = get_current_adk_user_id(request)
            
            logger.info(f"Starting logout process - Session: {session_id}, ADK user: {adk_user_id}")
            
            # 1. 統合セッション管理での削除を試行
            unified_logout_success = False
            try:
                from auth.unified_session_manager import get_unified_session_manager
                unified_manager = get_unified_session_manager()
                
                if unified_manager.delete_unified_session(request):
                    unified_manager.clear_session_cookie(response)
                    logger.info(f"Unified logout completed - Session: {session_id}")
                    unified_logout_success = True
            except Exception as e:
                logger.warning(f"Unified logout failed, using fallback: {e}")
            
            # 2. フォールバック処理または追加クリーンアップ
            if not unified_logout_success:
                # ADKセッションを明示的にクリーンアップ
                if adk_user_id != "anonymous":
                    sync_manager.on_logout(session_id, adk_user_id)
                    logger.info(f"ADK sessions cleaned up for user: {adk_user_id}")
                
                # ログインセッションを削除
                session_manager.delete_session(session_id)
                session_manager.clear_session_cookie(response)
                
                logger.info(f"Fallback logout completed - Session: {session_id}")
            
            return {
                "success": True, 
                "message": "Logged out successfully",
                "session_id": session_id,
                "adk_user_id": adk_user_id,
                "unified_logout": unified_logout_success
            }
        else:
            # セッションがない場合でもクッキーをクリア
            session_manager.clear_session_cookie(response)
            return {"success": True, "message": "No active session found"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        # エラーが発生してもクッキーはクリアする
        try:
            from auth.session_auth import get_session_auth_manager
            session_manager = get_session_auth_manager()
            session_manager.clear_session_cookie(response)
        except:
            pass
        return {"success": False, "error": str(e)}

# Google OAuth2.0認証開始エンドポイント
@app.get("/auth/start")
async def start_oauth(request: Request):
    """Google OAuth2.0認証を開始（セッションベース）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        from auth.session_auth import get_session_auth_manager
        
        # セッションベースの認証状態をチェック
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info:
            return {
                "success": True,
                "message": "Already authenticated",
                "authenticated": True
            }
        
        # 認証URLを生成（認証フロー開始）
        auth_manager = get_auth_manager()
        if not auth_manager.client_secrets_file or not os.path.exists(auth_manager.client_secrets_file):
            return {"error": "OAuth client secrets not configured"}
        
        from google_auth_oauthlib.flow import Flow
        
        flow = Flow.from_client_secrets_file(
            auth_manager.client_secrets_file,
            scopes=auth_manager.scopes
        )
        flow.redirect_uri = AppConfig.GOOGLE_OAUTH_REDIRECT_URI
        
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            include_granted_scopes='true'
        )
        
        return create_success_response(
            "Please visit the auth_url to complete authentication",
            auth_url=auth_url
        )
        
    except Exception as e:
        return handle_auth_error(e, "OAuth start")

# MCP ADA認証ステータス確認エンドポイント
@app.get("/auth/mcp-ada/status")
async def mcp_ada_auth_status():
    """MCP ADA認証ステータスを確認（ユーザー共通）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # MCP用のユーザーIDを取得（ユーザー共通）
        user_id = get_current_user_id_for_mcp()
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
    """MCP ADA OAuth2.0認証を開始（ユーザー共通）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # MCP用のユーザーIDを取得（ユーザー共通）
        user_id = get_current_user_id_for_mcp()
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
            auth_result = auth_manager.generate_auth_url()
            if len(auth_result) == 3:
                auth_url, state, _ = auth_result  # code_verifierは使用しないため無視
            else:
                auth_url, state = auth_result
            
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
    """MCP ADA認証コールバック処理（ユーザー共通）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # MCP用のユーザーIDを取得（ユーザー共通）
        user_id = get_current_user_id_for_mcp()
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
    """MCP ADA認証情報をクリア（ユーザー共通）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # MCP用のユーザーIDを取得（ユーザー共通）
        user_id = get_current_user_id_for_mcp()
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

# セッション統計情報取得エンドポイント
@app.get("/auth/sessions/stats")
async def get_session_stats(request: Request):
    """統合セッション統計情報を取得"""
    try:
        from auth.session_sync_manager import get_session_sync_manager
        
        sync_manager = get_session_sync_manager()
        adk_user_id = get_current_adk_user_id(request)
        
        return sync_manager.get_session_stats(adk_user_id if adk_user_id != "anonymous" else None)
    except Exception as e:
        logger.error(f"Failed to get session stats: {e}")
        return {"error": str(e)}

# 孤立セッションクリーンアップエンドポイント
@app.post("/auth/sessions/cleanup")
async def cleanup_orphaned_sessions():
    """孤立したADKセッション（対応するログインセッションがない）をクリーンアップ"""
    try:
        from auth.session_sync_manager import get_session_sync_manager
        
        sync_manager = get_session_sync_manager()
        deleted_count = sync_manager.cleanup_orphaned_adk_sessions()
        
        return {
            "success": True,
            "deleted_sessions": deleted_count,
            "message": f"Cleaned up {deleted_count} orphaned ADK sessions"
        }
    except Exception as e:
        logger.error(f"Failed to cleanup orphaned sessions: {e}")
        return {"success": False, "error": str(e)}

# ADKセッション状況確認エンドポイント
@app.get("/auth/adk-sessions/stats")
async def get_adk_session_stats(request: Request):
    """ADKセッションの統計情報を取得"""
    try:
        import sqlite3
        
        # 現在のユーザーのADKユーザーIDを取得
        adk_user_id = get_current_adk_user_id(request)
        
        # ADKデータベースに接続
        conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        # 全体の統計
        cursor.execute("SELECT COUNT(DISTINCT user_id) as total_users, COUNT(*) as total_sessions FROM sessions")
        total_stats = cursor.fetchone()
        
        # 現在のユーザーのセッション統計
        cursor.execute("""
            SELECT COUNT(*) as user_sessions, MAX(update_time) as last_activity 
            FROM sessions 
            WHERE user_id = ?
        """, (adk_user_id,))
        user_stats = cursor.fetchone()
        
        # ユーザーIDごとのセッション数
        cursor.execute("""
            SELECT user_id, COUNT(*) as session_count 
            FROM sessions 
            GROUP BY user_id
            ORDER BY session_count DESC
        """)
        user_breakdown = cursor.fetchall()
        
        conn.close()
        
        return {
            "current_adk_user_id": adk_user_id,
            "total_users": total_stats[0] if total_stats else 0,
            "total_adk_sessions": total_stats[1] if total_stats else 0,
            "current_user_sessions": user_stats[0] if user_stats else 0,
            "last_activity": user_stats[1] if user_stats else None,
            "user_breakdown": [
                {"user_id": row[0], "session_count": row[1]} 
                for row in user_breakdown
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get ADK session stats: {e}")
        return {"error": str(e)}

# 統合セッション管理エンドポイント
@app.get("/auth/unified/session")
async def get_unified_session(request: Request):
    """現在の統合セッション情報を取得"""
    try:
        from auth.unified_session_manager import get_unified_session_manager
        
        unified_manager = get_unified_session_manager()
        session_info = unified_manager.get_unified_session_info(request)
        
        if session_info:
            return {
                "authenticated": True,
                "session_info": session_info
            }
        else:
            return {"authenticated": False}
            
    except Exception as e:
        logger.error(f"Failed to get unified session: {e}")
        return {"authenticated": False, "error": str(e)}

@app.get("/auth/unified/adk-sessions/{adk_user_id}")
async def get_adk_sessions_details(adk_user_id: str):
    """指定ユーザーのADKセッション詳細を取得"""
    try:
        from auth.unified_session_manager import get_unified_session_manager
        
        unified_manager = get_unified_session_manager()
        sessions = unified_manager.get_adk_session_details(adk_user_id)
        
        return {
            "adk_user_id": adk_user_id,
            "sessions": sessions,
            "session_count": len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Failed to get ADK sessions details: {e}")
        return {"error": str(e)}

@app.get("/auth/chats")
async def get_current_user_chats(request: Request):
    """現在のユーザーのチャット一覧を取得"""
    try:
        from auth.unified_session_manager import get_unified_session_manager
        
        # 現在のユーザーのADKユーザーIDを取得
        adk_user_id = get_current_adk_user_id(request)
        if adk_user_id == "anonymous":
            return {"error": "Authentication required", "authenticated": False}
        
        unified_manager = get_unified_session_manager()
        sessions = unified_manager.get_adk_session_details(adk_user_id)
        
        return {
            "authenticated": True,
            "adk_user_id": adk_user_id,
            "chats": sessions,
            "chat_count": len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Failed to get current user chats: {e}")
        return {"error": str(e), "authenticated": False}

@app.get("/auth/chats/with-history")
async def get_current_user_chats_with_history(request: Request, include_archived: bool = False):
    """現在のユーザーのチャット一覧を履歴情報と共に取得"""
    try:
        import sqlite3
        from auth.unified_session_manager import get_unified_session_manager
        
        # 現在のユーザーのADKユーザーIDを取得
        adk_user_id = get_current_adk_user_id(request)
        if adk_user_id == "anonymous":
            return {"error": "Authentication required", "authenticated": False}
        
        # ADKセッション（チャット）の詳細を取得
        unified_manager = get_unified_session_manager()
        sessions = unified_manager.get_adk_session_details(adk_user_id)
        
        # 各セッションにメッセージ履歴情報を追加
        conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        enhanced_chats = []
        for session in sessions:
            session_id = session["session_id"]
            
            # アクティブなメッセージ数を取得
            cursor.execute("""
                SELECT COUNT(*) as message_count, MAX(timestamp) as last_message_time
                FROM events 
                WHERE user_id = ? AND session_id = ? AND grounding_metadata NOT LIKE '%archived_at%'
            """, (adk_user_id, session_id))
            active_stats = cursor.fetchone()
            
            # アーカイブされたメッセージ数を取得（オプション）
            archived_count = 0
            if include_archived:
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM events 
                    WHERE user_id = ? AND session_id = ? AND grounding_metadata LIKE '%archived_at%'
                """, (adk_user_id, session_id))
                archived_result = cursor.fetchone()
                archived_count = archived_result[0] if archived_result else 0
            
            enhanced_chat = {
                **session,
                "message_count": active_stats[0] if active_stats else 0,
                "last_message_time": active_stats[1] if active_stats else None,
                "has_messages": (active_stats[0] if active_stats else 0) > 0
            }
            
            if include_archived:
                enhanced_chat["archived_message_count"] = archived_count
            
            enhanced_chats.append(enhanced_chat)
        
        conn.close()
        
        # チャットを最新メッセージ順にソート
        enhanced_chats.sort(key=lambda x: x.get("last_message_time") or x.get("updated_at", ""), reverse=True)
        
        return {
            "authenticated": True,
            "adk_user_id": adk_user_id,
            "chats": enhanced_chats,
            "chat_count": len(enhanced_chats),
            "include_archived": include_archived
        }
        
    except Exception as e:
        logger.error(f"Failed to get current user chats with history: {e}")
        return {"error": str(e), "authenticated": False}

@app.delete("/auth/chats/{session_id}")
async def delete_chat_session(session_id: str, request: Request):
    """指定されたチャットセッションを削除"""
    try:
        import sqlite3
        
        # 現在のユーザーのADKユーザーIDを取得
        adk_user_id = get_current_adk_user_id(request)
        if adk_user_id == "anonymous":
            return {"error": "Authentication required", "authenticated": False}
        
        # セッションが存在し、現在のユーザーのものかを確認
        conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM sessions 
            WHERE id = ? AND user_id = ?
        """, (session_id, adk_user_id))
        
        session_exists = cursor.fetchone()[0] > 0
        
        if not session_exists:
            conn.close()
            return {
                "success": False, 
                "error": "Chat session not found or access denied",
                "session_id": session_id
            }
        
        # セッションとその関連データを削除
        # FOREIGN KEY制約により、関連するeventsも自動削除される
        cursor.execute("DELETE FROM sessions WHERE id = ? AND user_id = ?", (session_id, adk_user_id))
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        if deleted_count > 0:
            logger.info(f"Deleted chat session {session_id} for user {adk_user_id}")
            return {
                "success": True,
                "message": "Chat session deleted successfully",
                "session_id": session_id
            }
        else:
            return {
                "success": False,
                "error": "Failed to delete chat session",
                "session_id": session_id
            }
        
    except Exception as e:
        logger.error(f"Failed to delete chat session {session_id}: {e}")
        return {"success": False, "error": str(e)}

@app.get("/auth/debug/user-info")
async def debug_user_info(request: Request):
    """デバッグ用：現在のユーザー識別情報を詳細表示"""
    try:
        from auth.session_auth import get_session_auth_manager
        
        # セッション情報を取得
        session_manager = get_session_auth_manager()
        session_id = session_manager.get_session_id_from_request(request)
        user_info = session_manager.get_user_info(request)
        
        # ADKユーザーID生成
        adk_user_id = get_current_adk_user_id(request)
        
        # ミドルウェアからの情報
        middleware_adk_user_id = "unknown"
        try:
            from middleware import get_user_id_for_adk
            middleware_adk_user_id = get_user_id_for_adk(request)
        except Exception as e:
            middleware_adk_user_id = f"error: {str(e)}"
        
        # emailからハッシュを直接計算
        email_hash = "no_email"
        if user_info and user_info.get("email"):
            import hashlib
            email = user_info["email"]
            hash_object = hashlib.sha256(email.encode('utf-8'))
            email_hash = hash_object.hexdigest()[:16]
        
        return {
            "session_id": session_id,
            "user_info": user_info,
            "adk_user_id_main": adk_user_id,
            "adk_user_id_middleware": middleware_adk_user_id,
            "email_hash_direct": email_hash,
            "cookies": dict(request.cookies),
            "authenticated": user_info is not None,
            "request_state": {
                "has_state": hasattr(request, 'state'),
                "adk_user_id_from_state": getattr(request.state, 'adk_user_id', 'not_set') if hasattr(request, 'state') else 'no_state'
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get debug user info: {e}")
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/auth/debug/sessions-comparison")
async def debug_sessions_comparison(request: Request):
    """デバッグ用：セッション管理システムの比較"""
    try:
        import sqlite3
        from auth.session_auth import get_session_auth_manager
        from auth.unified_session_manager import get_unified_session_manager
        
        # 現在のユーザー情報
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        login_session_id = session_manager.get_session_id_from_request(request)
        
        if not user_info:
            return {"error": "Not authenticated", "authenticated": False}
        
        email = user_info.get("email")
        if not email:
            return {"error": "No email found", "user_info": user_info}
        
        # ADKユーザーIDの生成
        import hashlib
        hash_object = hashlib.sha256(email.encode('utf-8'))
        expected_adk_user_id = hash_object.hexdigest()[:16]
        
        # 各種ユーザーID取得方法の比較
        adk_user_id_main = get_current_adk_user_id(request)
        
        # データベースの実際のデータを確認
        conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        # 全セッション情報
        cursor.execute("SELECT user_id, id, app_name, create_time, update_time FROM sessions")
        all_sessions = cursor.fetchall()
        
        # 現在のユーザーのセッション
        cursor.execute("SELECT user_id, id, app_name, create_time, update_time FROM sessions WHERE user_id = ?", (expected_adk_user_id,))
        user_sessions = cursor.fetchall()
        
        # eventsテーブルの確認
        cursor.execute("SELECT DISTINCT user_id FROM events")
        users_with_events = cursor.fetchall()
        
        # 現在のユーザーのイベント数
        cursor.execute("SELECT COUNT(*) FROM events WHERE user_id = ?", (expected_adk_user_id,))
        user_event_count = cursor.fetchone()[0]
        
        conn.close()
        
        # 統合セッション情報
        unified_manager = get_unified_session_manager()
        unified_session_info = unified_manager.get_unified_session_info(request)
        
        return {
            "authentication": {
                "authenticated": True,
                "email": email,
                "user_info": user_info,
                "login_session_id": login_session_id
            },
            "adk_user_ids": {
                "expected": expected_adk_user_id,
                "from_main_function": adk_user_id_main,
                "match": expected_adk_user_id == adk_user_id_main
            },
            "database_state": {
                "total_sessions": len(all_sessions),
                "user_sessions": len(user_sessions),
                "user_event_count": user_event_count,
                "all_sessions": [
                    {
                        "user_id": s[0], 
                        "session_id": s[1], 
                        "app_name": s[2],
                        "created": s[3],
                        "updated": s[4]
                    } for s in all_sessions
                ],
                "user_sessions": [
                    {
                        "user_id": s[0], 
                        "session_id": s[1], 
                        "app_name": s[2],
                        "created": s[3],
                        "updated": s[4]
                    } for s in user_sessions
                ],
                "users_with_events": [u[0] for u in users_with_events]
            },
            "unified_session": unified_session_info
        }
        
    except Exception as e:
        logger.error(f"Failed to debug sessions comparison: {e}")
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/auth/debug/artifact-paths")
async def debug_artifact_paths(request: Request):
    """Artifact保存パスのデバッグ情報を取得"""
    try:
        import sqlite3
        
        # セッションデータベースから現在の情報を取得
        conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        # 最新のセッション情報を取得
        cursor.execute("""
            SELECT id, user_id, app_name, create_time, update_time 
            FROM sessions 
            WHERE app_name = 'document_creating_agent'
            ORDER BY update_time DESC 
            LIMIT 10
        """)
        
        recent_sessions = []
        for row in cursor.fetchall():
            session_id, user_id, app_name, create_time, update_time = row
            recent_sessions.append({
                "session_id": session_id,
                "user_id": user_id,
                "app_name": app_name,
                "create_time": create_time,
                "update_time": update_time
            })
        
        conn.close()
        
        # GCS情報の取得を試行
        gcs_info = {
            "bucket_name": ARTIFACT_URL.replace("gs://", ""),
            "artifact_service_uri": ARTIFACT_URL
        }
        
        # 現在のログイン情報
        from auth.session_auth import get_session_auth_manager
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        current_user_info = None
        if user_info:
            email = user_info.get("email")
            if email:
                import hashlib
                normalized_email = email.strip().lower()
                hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
                adk_user_id = hash_object.hexdigest()[:16]
                
                current_user_info = {
                    "email": email,
                    "adk_user_id": adk_user_id,
                    "login_session_id": session_manager.get_session_id_from_request(request)
                }
        
        return {
            "current_user": current_user_info,
            "recent_sessions": recent_sessions,
            "gcs_info": gcs_info,
            "expected_artifact_paths": [
                f"{gcs_info['bucket_name']}/document_creating_agent/{session['user_id']}/{session['session_id']}/[filename]"
                for session in recent_sessions[:3]
            ],
            "debug_note": "実際のArtifact保存時には、ADKが内部的にユーザーIDとセッションIDを決定します"
        }
        
    except Exception as e:
        logger.error(f"Failed to get artifact debug info: {e}")
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/auth/verify/consistency")
async def verify_user_id_consistency(request: Request):
    """ユーザーID生成の一貫性を検証"""
    try:
        from auth.session_auth import get_session_auth_manager
        from auth.unified_session_manager import get_unified_session_manager
        from auth.session_sync_manager import get_session_sync_manager
        from middleware import get_user_id_for_adk
        import hashlib
        
        # セッション情報を取得
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if not user_info or not user_info.get("email"):
            return {"error": "Not authenticated or no email", "authenticated": False}
        
        email = user_info["email"]
        normalized_email = email.strip().lower()
        
        # 各システムでのユーザーID生成をテスト
        results = {}
        
        # 1. main.py の get_current_adk_user_id
        results["main_function"] = get_current_adk_user_id(request)
        
        # 2. middleware の get_user_id_for_adk
        results["middleware"] = get_user_id_for_adk(request)
        
        # 3. 統合セッション管理
        unified_manager = get_unified_session_manager()
        results["unified_manager"] = unified_manager._get_stable_adk_user_id(email)
        
        # 4. セッション同期管理
        sync_manager = get_session_sync_manager()
        results["sync_manager"] = sync_manager._get_stable_adk_user_id(email)
        
        # 5. 直接計算（期待値）
        hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
        expected = hash_object.hexdigest()[:16]
        results["expected"] = expected
        
        # 一貫性チェック
        all_values = list(results.values())
        is_consistent = all(value == expected for value in all_values)
        
        # 不一致の特定
        inconsistent_systems = []
        for system, value in results.items():
            if value != expected:
                inconsistent_systems.append({"system": system, "value": value, "expected": expected})
        
        return {
            "email": email,
            "normalized_email": normalized_email,
            "results": results,
            "is_consistent": is_consistent,
            "expected_value": expected,
            "inconsistent_systems": inconsistent_systems,
            "summary": {
                "total_systems": len(results),
                "consistent_systems": len([v for v in all_values if v == expected]),
                "inconsistent_systems": len(inconsistent_systems)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to verify user ID consistency: {e}")
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.post("/auth/unified/adk-session/create")
async def force_create_adk_session(request: Request, app_name: str = "document_creating_agent"):
    """ADKセッションを強制作成（管理・テスト用）"""
    try:
        from auth.unified_session_manager import get_unified_session_manager
        
        unified_manager = get_unified_session_manager()
        session_info = unified_manager.get_unified_session_info(request)
        
        if not session_info:
            return {"success": False, "error": "Not authenticated"}
        
        adk_user_id = session_info["adk_user_id"]
        session_id = unified_manager.force_create_adk_session(adk_user_id, app_name)
        
        if session_id:
            return {
                "success": True,
                "session_id": session_id,
                "adk_user_id": adk_user_id,
                "app_name": app_name
            }
        else:
            return {"success": False, "error": "Failed to create ADK session"}
        
    except Exception as e:
        logger.error(f"Failed to force create ADK session: {e}")
        return {"success": False, "error": str(e)}

@app.get("/auth/unified/stats")
async def get_unified_stats():
    """統合セッション統計を取得"""
    try:
        from auth.unified_session_manager import get_unified_session_manager
        
        unified_manager = get_unified_session_manager()
        return unified_manager.get_unified_stats()
        
    except Exception as e:
        logger.error(f"Failed to get unified stats: {e}")
        return {"error": str(e)}

# チャット履歴管理エンドポイント
@app.get("/auth/chat-history/archived")
async def get_archived_chat_history(request: Request, limit: int = 50):
    """現在のユーザーのアーカイブされたチャット履歴を取得"""
    try:
        from auth.session_sync_manager import get_session_sync_manager
        
        adk_user_id = get_current_adk_user_id(request)
        if adk_user_id == "anonymous":
            return {"error": "Authentication required"}
        
        sync_manager = get_session_sync_manager()
        history = sync_manager.get_archived_chat_history(adk_user_id, limit)
        
        return {
            "adk_user_id": adk_user_id,
            "archived_history": history,
            "count": len(history)
        }
        
    except Exception as e:
        logger.error(f"Failed to get archived chat history: {e}")
        return {"error": str(e)}

@app.get("/auth/chat-history/stats")
async def get_archived_chat_stats():
    """アーカイブチャット統計情報を取得"""
    try:
        from auth.session_sync_manager import get_session_sync_manager
        
        sync_manager = get_session_sync_manager()
        return sync_manager.get_archived_chat_stats()
        
    except Exception as e:
        logger.error(f"Failed to get archived chat stats: {e}")
        return {"error": str(e)}

@app.post("/auth/chat-history/cleanup")
async def cleanup_old_archived_chats(days_to_keep: int = 90):
    """古いアーカイブチャットをクリーンアップ"""
    try:
        from auth.session_sync_manager import get_session_sync_manager
        
        sync_manager = get_session_sync_manager()
        deleted_count = sync_manager.cleanup_old_archived_chats(days_to_keep)
        
        return {
            "success": True,
            "deleted_count": deleted_count,
            "days_kept": days_to_keep,
            "message": f"Cleaned up {deleted_count} old archived chats (older than {days_to_keep} days)"
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old archived chats: {e}")
        return {"success": False, "error": str(e)}

@app.get("/download/artifact/{app_name}/{user_id}/{session_id}/{artifact_name}")
async def download_artifact_stream(
    app_name: str,
    user_id: str, 
    session_id: str,
    artifact_name: str,
    version: Optional[int] = None
):
    """任意のArtifactをストリーミング形式でダウンロード"""
    try:
        logger.info(f"Download request: app={app_name}, user={user_id}, session={session_id}, file={artifact_name}, version={version}")
        
        # GCS Artifact Service を直接使用
        from google.adk.artifacts import GcsArtifactService
        
        # GCSバケット名を設定から取得
        gcs_bucket_name = ARTIFACT_URL.replace("gs://", "")  # "gs://dev-datap-agent-bucket" -> "dev-datap-agent-bucket"
        logger.info(f"Using GCS bucket: {gcs_bucket_name}")
        
        try:
            # GCS Artifact Service の初期化
            gcs_service = GcsArtifactService(bucket_name=gcs_bucket_name)
            
            # 複数のパターンでArtifactの読み込みを試行
            artifact = None
            attempted_paths = []
            
            # パターン1: 指定されたパラメータをそのまま使用
            try:
                logger.info(f"Trying pattern 1: app={app_name}, user={user_id}, session={session_id}")
                if version is not None:
                    artifact = await gcs_service.load_artifact(
                        app_name=app_name,
                        user_id=user_id,
                        session_id=session_id,
                        filename=artifact_name,
                        version=version
                    )
                else:
                    artifact = await gcs_service.load_artifact(
                        app_name=app_name,
                        user_id=user_id,
                        session_id=session_id,
                        filename=artifact_name
                    )
                attempted_paths.append(f"{app_name}/{user_id}/{session_id}/{artifact_name}")
                if artifact:
                    logger.info("Found artifact with pattern 1")
            except Exception as e1:
                logger.warning(f"Pattern 1 failed: {e1}")
            
            # パターン2: session_idが問題の場合、最近のセッションで試行
            if not artifact and session_id == "unknown":
                try:
                    import sqlite3
                    conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
                    cursor = conn.cursor()
                    
                    # 該当user_idの最新セッションを取得
                    cursor.execute("""
                        SELECT id FROM sessions 
                        WHERE user_id = ? AND app_name = ?
                        ORDER BY update_time DESC 
                        LIMIT 1
                    """, (user_id, app_name))
                    
                    result = cursor.fetchone()
                    if result:
                        actual_session_id = result[0]
                        logger.info(f"Trying pattern 2 with actual session: {actual_session_id}")
                        
                        if version is not None:
                            artifact = await gcs_service.load_artifact(
                                app_name=app_name,
                                user_id=user_id,
                                session_id=actual_session_id,
                                filename=artifact_name,
                                version=version
                            )
                        else:
                            artifact = await gcs_service.load_artifact(
                                app_name=app_name,
                                user_id=user_id,
                                session_id=actual_session_id,
                                filename=artifact_name
                            )
                        attempted_paths.append(f"{app_name}/{user_id}/{actual_session_id}/{artifact_name}")
                        if artifact:
                            logger.info(f"Found artifact with pattern 2 (actual session: {actual_session_id})")
                    
                    conn.close()
                except Exception as e2:
                    logger.warning(f"Pattern 2 failed: {e2}")
            
            # パターン3: user_idが問題の場合、emailからの変換を試行
            if not artifact and user_id == "test":
                try:
                    import sqlite3
                    conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
                    cursor = conn.cursor()
                    
                    # 最近のアクティブユーザーを取得
                    cursor.execute("""
                        SELECT user_id, id FROM sessions 
                        WHERE app_name = ?
                        ORDER BY update_time DESC 
                        LIMIT 5
                    """)
                    
                    results = cursor.fetchall()
                    for db_user_id, db_session_id in results:
                        try:
                            logger.info(f"Trying pattern 3 with user={db_user_id}, session={db_session_id}")
                            
                            if version is not None:
                                artifact = await gcs_service.load_artifact(
                                    app_name=app_name,
                                    user_id=db_user_id,
                                    session_id=db_session_id,
                                    filename=artifact_name,
                                    version=version
                                )
                            else:
                                artifact = await gcs_service.load_artifact(
                                    app_name=app_name,
                                    user_id=db_user_id,
                                    session_id=db_session_id,
                                    filename=artifact_name
                                )
                            attempted_paths.append(f"{app_name}/{db_user_id}/{db_session_id}/{artifact_name}")
                            if artifact:
                                logger.info(f"Found artifact with pattern 3 (user={db_user_id}, session={db_session_id})")
                                break
                        except Exception as e3:
                            logger.debug(f"Pattern 3 attempt failed for user={db_user_id}: {e3}")
                    
                    conn.close()
                except Exception as e3:
                    logger.warning(f"Pattern 3 failed: {e3}")
            
            if not artifact:
                logger.error(f"Artifact not found after trying all patterns. Attempted paths: {attempted_paths}")
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404, 
                    detail=f"Artifact not found: {artifact_name}. Tried paths: {attempted_paths}"
                )
                
        except Exception as gcs_error:
            logger.error(f"Failed to load artifact using GCS service: {gcs_error}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=f"Failed to load artifact from GCS: {str(gcs_error)}")
        
        # バイナリデータを取得
        file_data = None
        mime_type = "application/octet-stream"
        
        if artifact and hasattr(artifact, 'inline_data') and artifact.inline_data:
            file_data = artifact.inline_data.data
            if hasattr(artifact.inline_data, 'mime_type') and artifact.inline_data.mime_type:
                mime_type = artifact.inline_data.mime_type
        elif hasattr(artifact, 'data'):
            file_data = artifact.data
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="Unable to extract file data from artifact")
        
        # バイナリデータの確認
        if file_data is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="No file data found in artifact")
        
        # bytes型でない場合は変換
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        elif not isinstance(file_data, (bytes, bytearray)):
            file_data = str(file_data).encode('utf-8')
        
        # ファイル拡張子からMIMEタイプを決定（inline_dataから取得できない場合のフォールバック）
        if mime_type == "application/octet-stream":
            def get_mime_type_from_extension(filename: str) -> str:
                """ファイル拡張子からMIMEタイプを取得"""
                extension = filename.lower().split('.')[-1] if '.' in filename else ''
                mime_types = {
                    'csv': 'text/csv',
                    'txt': 'text/plain',
                    'json': 'application/json',
                    'pdf': 'application/pdf',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'xls': 'application/vnd.ms-excel',
                    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'doc': 'application/msword',
                    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'ppt': 'application/vnd.ms-powerpoint',
                    'png': 'image/png',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'gif': 'image/gif',
                    'svg': 'image/svg+xml',
                    'html': 'text/html',
                    'xml': 'application/xml',
                    'zip': 'application/zip',
                    'tar': 'application/x-tar',
                    'gz': 'application/gzip'
                }
                return mime_types.get(extension, 'application/octet-stream')
            
            mime_type = get_mime_type_from_extension(artifact_name)
        
        # ストリーミングレスポンスを作成
        def generate():
            yield file_data
        
        logger.info(f"Streaming artifact download: {artifact_name} (size: {len(file_data)} bytes, mime_type: {mime_type})")
        
        return StreamingResponse(
            generate(),
            media_type=mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{artifact_name}\"",
                "Content-Length": str(len(file_data)),
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to stream artifact download: {e}")
        import traceback
        traceback.print_exc()
        
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to download artifact: {str(e)}"
        )

@app.get("/download/artifact/by-invocation/{invocation_id}/{artifact_name}")
async def download_artifact_by_invocation(
    invocation_id: str,
    artifact_name: str,
    version: Optional[int] = None
):
    """invocationIdを使用してArtifactをダウンロード"""
    try:
        # GCS Artifact Service を直接使用
        from google.adk.artifacts import GcsArtifactService
        
        # GCSバケット名を設定から取得
        gcs_bucket_name = ARTIFACT_URL.replace("gs://", "")
        
        try:
            # chat session情報デバッグ
            from auth.session_sync_manager import get_session_sync_manager
            sync_manager = get_session_sync_manager()
            session_info = sync_manager.get_session_info(invocation_id)
            logger.info(f"Session info: {session_info}")



            # GCS Artifact Service の初期化
            gcs_service = GcsArtifactService(bucket_name=gcs_bucket_name)
            
            # invocationIdベースでArtifactを検索
            # invocationIdからapp_name, user_id, session_idを推測する必要があるが、
            # 実際にはGCSの構造に依存する
            
            # まず、一般的なパターンでの検索を試行
            app_name = "document_creating_agent"  # 固定値として使用
            
            # invocationIdから可能な限り情報を抽出
            # 実際の実装では、invocationIdとセッション情報のマッピングが必要
            
            # フォールバック: 既知のパターンで検索
            # 通常はinvocationIdとartifact情報のマッピングテーブルが必要だが、
            # ここでは直接的なアプローチを取る
            
            # より直接的なアプローチ: invocationIdをsession_idとして使用
            artifact = None
            
            # 方法1: invocationIdをsession_idとして使用して検索
            try:
                # ADK安定ユーザーID生成関数（main.pyの get_current_adk_user_id と同一）
                def get_adk_stable_user_id_from_email(email: str) -> str:
                    """emailからADK用の安定したユーザーID（16文字のハッシュ）を生成"""
                    import hashlib
                    normalized_email = email.strip().lower()
                    hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
                    return hash_object.hexdigest()[:16]
                
                # リクエストが利用できないため、複数のユーザーIDパターンを試行
                user_id_candidates = []
                
                # 1. データベースから最近のユーザーIDを取得し、email形式は変換
                try:
                    import sqlite3
                    conn = sqlite3.connect(SESSION_DB_URL.replace('sqlite:///', ''))
                    cursor = conn.cursor()
                    
                    # 最近のセッションからユーザーIDを取得
                    cursor.execute("""
                        SELECT DISTINCT user_id FROM sessions 
                        WHERE app_name = ? 
                        ORDER BY update_time DESC 
                        LIMIT 20
                    """, (app_name,))
                    recent_users = [row[0] for row in cursor.fetchall()]
                    
                    # email形式のものはADK stable user IDに変換して追加
                    for user_id in recent_users:
                        if isinstance(user_id, str) and '@' in user_id:
                            # email形式の場合は変換版も追加
                            adk_user_id = get_adk_stable_user_id_from_email(user_id)
                            user_id_candidates.append(adk_user_id)
                            # 元のemail形式も念のため保持
                            user_id_candidates.append(user_id)
                        else:
                            user_id_candidates.append(user_id)
                    
                    conn.close()
                    logger.info(f"Found {len(recent_users)} recent users from database")
                except Exception as db_error:
                    logger.warning(f"Failed to get recent users from database: {db_error}")
                
                # 2. フォールバックパターン
                user_id_candidates.extend(["anonymous", "test_user"])
                
                # 3. 重複除去
                user_id_candidates = list(dict.fromkeys(user_id_candidates))
                
                # 各ユーザーIDでartifactを検索
                for candidate_user_id in user_id_candidates:
                    try:
                        artifact = await gcs_service.load_artifact(
                            app_name=app_name,
                            user_id=candidate_user_id,
                            session_id=invocation_id,
                            filename=artifact_name,
                            version=version
                        )
                        
                        if artifact:
                            logger.info(f"Found artifact using user_id={candidate_user_id}, session_id={invocation_id}")
                            break
                    except Exception as search_error:
                        logger.debug(f"Search failed for user_id={candidate_user_id}, session_id={invocation_id}: {search_error}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Failed to load artifact with invocation_id as session_id: {e}")
            
            # 方法2: 既存のsession情報を使用してinvocationId内のartifactを探す
            if not artifact:
                try:
                    # 最近のセッション情報を使用
                    import glob
                    import os
                    
                    # GCSから直接検索する代替方法が必要
                    # ここでは簡単な方法として、よく使われるパターンを試行
                    common_users = ["anonymous", user_id] if user_id else ["anonymous"]
                    common_sessions = [invocation_id, f"session_{datetime.now().strftime('%Y%m%d')}", "test_session"]
                    
                    for test_user in common_users:
                        for test_session in common_sessions:
                            try:
                                artifact = await gcs_service.load_artifact(
                                    app_name=app_name,
                                    user_id=test_user,
                                    session_id=test_session,
                                    filename=artifact_name,
                                    version=version
                                )
                                if artifact:
                                    logger.info(f"Found artifact with user={test_user}, session={test_session}")
                                    break
                            except:
                                continue
                        if artifact:
                            break
                            
                except Exception as e:
                    logger.warning(f"Failed alternative search method: {e}")
            
            if not artifact:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404, 
                    detail=f"Artifact not found: {artifact_name} for invocation {invocation_id}"
                )
                
        except Exception as gcs_error:
            logger.error(f"Failed to load artifact using GCS service: {gcs_error}")
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=f"Failed to load artifact from GCS: {str(gcs_error)}")
        
        # バイナリデータを取得
        file_data = None
        mime_type = "application/octet-stream"
        
        if artifact and hasattr(artifact, 'inline_data') and artifact.inline_data:
            file_data = artifact.inline_data.data
            if hasattr(artifact.inline_data, 'mime_type') and artifact.inline_data.mime_type:
                mime_type = artifact.inline_data.mime_type
        elif hasattr(artifact, 'data'):
            file_data = artifact.data
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="Unable to extract file data from artifact")
        
        # バイナリデータの確認
        if file_data is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail="No file data found in artifact")
        
        # bytes型でない場合は変換
        if isinstance(file_data, str):
            file_data = file_data.encode('utf-8')
        elif not isinstance(file_data, (bytes, bytearray)):
            file_data = str(file_data).encode('utf-8')
        
        # ファイル拡張子からMIMEタイプを決定（inline_dataから取得できない場合のフォールバック）
        if mime_type == "application/octet-stream":
            def get_mime_type_from_extension(filename: str) -> str:
                """ファイル拡張子からMIMEタイプを取得"""
                extension = filename.lower().split('.')[-1] if '.' in filename else ''
                mime_types = {
                    'csv': 'text/csv',
                    'txt': 'text/plain',
                    'json': 'application/json',
                    'pdf': 'application/pdf',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'xls': 'application/vnd.ms-excel',
                    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'doc': 'application/msword',
                    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'ppt': 'application/vnd.ms-powerpoint',
                    'png': 'image/png',
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'gif': 'image/gif',
                    'svg': 'image/svg+xml',
                    'html': 'text/html',
                    'xml': 'application/xml',
                    'zip': 'application/zip',
                    'tar': 'application/x-tar',
                    'gz': 'application/gzip'
                }
                return mime_types.get(extension, 'application/octet-stream')
            
            mime_type = get_mime_type_from_extension(artifact_name)
        
        # ストリーミングレスポンスを作成
        def generate():
            yield file_data
        
        logger.info(f"Streaming artifact download by invocation: {artifact_name} (invocation: {invocation_id}, size: {len(file_data)} bytes, mime_type: {mime_type})")
        
        return StreamingResponse(
            generate(),
            media_type=mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{artifact_name}\"",
                "Content-Length": str(len(file_data)),
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to stream artifact download by invocation: {e}")
        import traceback
        traceback.print_exc()
        
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to download artifact by invocation: {str(e)}"
        )

# セッションクリーンアップのバックグラウンドタスク
# Note: FastAPIのlifespanイベントを使用してバックグラウンドタスクを管理

if __name__ == "__main__":
    logger.info("Starting application...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        traceback.print_exc()