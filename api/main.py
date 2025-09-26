import os
import asyncio
import time
from contextlib import asynccontextmanager
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from shared.core.middleware import auth_middleware
from typing import Optional
import logging

# Import shared modules
from shared.core.config import AppConfig, LogConfig
from shared.services.app_utils import generate_adk_user_id
from shared.services.error_handlers import handle_auth_error, create_success_response

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
    from shared.auth.session_auth import get_session_auth_manager
    from shared.auth.session_sync_manager import get_session_sync_manager
    
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
async def lifespan(_app: FastAPI):
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

# Agent initialization is handled by the ADK framework via get_fast_api_app()

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


# CORS設定を最初に適用（認証ミドルウェアより前に）
app.add_middleware(
    CORSMiddleware,
    allow_origins=AppConfig.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 認証ミドルウェアを追加（CORSの後に）
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

# CORS設定は上記で適用済み

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
            from shared.auth.session_auth import get_session_auth_manager
            
            session_manager = get_session_auth_manager()
            user_info = session_manager.get_user_info(request)
            
            if user_info:
                return user_info.get("email", user_info.get("id"))
        
        # フォールバックとしてMCP認証を使用
        from shared.auth.google_auth import get_auth_manager
        
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
        from shared.auth.session_auth import get_session_auth_manager
        
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
# ADK User ID endpoint moved to auth_routes.py

# Google OAuth2.0コールバックエンドポイント
@app.get("/auth/callback")
async def oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
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
        from shared.auth.google_auth import get_auth_manager
        from shared.auth.session_auth import get_session_auth_manager
        
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
                        from shared.auth.unified_session_manager import get_unified_session_manager
                        unified_manager = get_unified_session_manager()
                        unified_session = unified_manager.create_unified_session(user_data, credentials)
                        session_id = unified_session["login_session_id"]
                        adk_user_id = unified_session["adk_user_id"]
                        logger.info(f"Using unified session management")
                    except Exception as e:
                        logger.warning(f"Unified session failed, using sync manager: {e}")
                        # フォールバック: 従来のセッション同期管理
                        from shared.auth.session_sync_manager import get_session_sync_manager
                        sync_manager = get_session_sync_manager()
                        session_id, adk_user_id = sync_manager.on_login(user_data, credentials)
                else:
                    # 従来のセッション同期管理を使用
                    from shared.auth.session_sync_manager import get_session_sync_manager
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

# Auth status endpoint moved to auth_routes.py

# Google OAuth2.0ログアウトエンドポイント
@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    """認証情報をクリア（セッションベース）"""
    try:
        from shared.auth.session_auth import get_session_auth_manager
        from shared.auth.session_sync_manager import get_session_sync_manager
        
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
                from shared.auth.unified_session_manager import get_unified_session_manager
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
            from shared.auth.session_auth import get_session_auth_manager
            session_manager = get_session_auth_manager()
            session_manager.clear_session_cookie(response)
        except:
            pass
        return {"success": False, "error": str(e)}

# OAuth start endpoint moved to auth_routes.py

# MCP ADA認証ステータス確認エンドポイント
@app.get("/auth/mcp-ada/status")
async def mcp_ada_auth_status():
    """MCP ADA認証ステータスを確認（ユーザー共通）"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
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
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
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
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
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
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
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
        from shared.auth.session_sync_manager import get_session_sync_manager
        
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
        from shared.auth.session_sync_manager import get_session_sync_manager
        
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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

# Debug endpoints moved to debug_routes.py

# Additional debug endpoints also moved to debug_routes.py

@app.get("/auth/verify/consistency")
async def verify_user_id_consistency(request: Request):
    """ユーザーID生成の一貫性を検証"""
    try:
        from shared.auth.session_auth import get_session_auth_manager
        from shared.auth.unified_session_manager import get_unified_session_manager
        from shared.auth.session_sync_manager import get_session_sync_manager
        from shared.core.middleware import get_user_id_for_adk
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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
        from shared.auth.unified_session_manager import get_unified_session_manager
        
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
        from shared.auth.session_sync_manager import get_session_sync_manager
        
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
        from shared.auth.session_sync_manager import get_session_sync_manager
        
        sync_manager = get_session_sync_manager()
        return sync_manager.get_archived_chat_stats()
        
    except Exception as e:
        logger.error(f"Failed to get archived chat stats: {e}")
        return {"error": str(e)}

@app.post("/auth/chat-history/cleanup")
async def cleanup_old_archived_chats(days_to_keep: int = 90):
    """古いアーカイブチャットをクリーンアップ"""
    try:
        from shared.auth.session_sync_manager import get_session_sync_manager
        
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
    from shared.services.artifact_service import ArtifactService
    
    service = ArtifactService()
    return await service.download_artifact(app_name, user_id, session_id, artifact_name, version)

@app.get("/download/artifact/by-invocation/{invocation_id}/{artifact_name}")
async def download_artifact_by_invocation(
    invocation_id: str,
    artifact_name: str,
    version: Optional[int] = None
):
    """invocationIdを使用してArtifactをダウンロード"""
    from shared.services.artifact_service import InvocationArtifactService
    
    service = InvocationArtifactService()
    return await service.download_artifact_by_invocation(invocation_id, artifact_name, version)

# セッションクリーンアップのバックグラウンドタスク
# Note: FastAPIのlifespanイベントを使用してバックグラウンドタスクを管理

# Include debug routes if debug mode is enabled
from api.routes.debug_routes import include_debug_routes
app = include_debug_routes(app)

# Include authentication routes
from api.routes.auth_routes import include_auth_routes
app = include_auth_routes(app)

# カスタムエンドポイント関数を定義
async def custom_list_apps():
    """利用可能なAIエージェント（アプリケーション）の一覧を返す"""
    try:
        import os
        import json
        
        logger.info("Custom /list-apps endpoint called")
        
        agents_dir = AppConfig.AGENT_DIR
        available_apps = []
        
        # ai_agents ディレクトリを探索
        if os.path.exists(agents_dir):
            for item in os.listdir(agents_dir):
                agent_path = os.path.join(agents_dir, item)
                
                # ディレクトリかつ、__init__.py または agent.py が存在するものをエージェントとみなす
                if os.path.isdir(agent_path):
                    init_py = os.path.join(agent_path, "__init__.py")
                    agent_py = os.path.join(agent_path, "agent.py")
                    
                    if os.path.exists(init_py) or os.path.exists(agent_py):
                        # エージェント設定ファイルがあれば読み込み
                        config_file = os.path.join(agent_path, "config.json")
                        agent_info = {
                            "name": item,
                            "id": item,
                            "display_name": item.replace("_", " ").title(),
                            "description": f"{item} AI Agent",
                            "available": True
                        }
                        
                        # config.json がある場合は設定を読み込み
                        if os.path.exists(config_file):
                            try:
                                with open(config_file, 'r', encoding='utf-8') as f:
                                    config = json.load(f)
                                    agent_info.update(config)
                            except Exception as e:
                                logger.warning(f"Failed to read config for {item}: {e}")
                        
                        available_apps.append(agent_info)
        
        logger.info(f"Found {len(available_apps)} available AI agents")
        result = {
            "apps": available_apps,
            "count": len(available_apps)
        }
        logger.info(f"Returning result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to list apps: {e}")
        return {
            "apps": [],
            "count": 0,
            "error": str(e)
        }

# 既存の /list-apps ルートがあれば削除して、カスタムエンドポイントを追加
try:
    # 既存のルートを探して削除
    routes_to_remove = []
    for route in app.routes:
        if hasattr(route, 'path') and route.path == "/list-apps":
            routes_to_remove.append(route)
    
    for route in routes_to_remove:
        app.routes.remove(route)
        logger.info("Removed existing /list-apps route")
    
    # カスタムルートを追加
    app.add_api_route("/list-apps", custom_list_apps, methods=["GET"], tags=["agents"])
    logger.info("Added custom /list-apps route")
    
except Exception as e:
    logger.warning(f"Failed to replace /list-apps route: {e}")
    # フォールバックとして通常のデコレータを使用
    @app.get("/list-apps")
    async def list_apps():
        return await custom_list_apps()

if __name__ == "__main__":
    logger.info("Starting application...")
    try:
        uvicorn.run(app, host=AppConfig.HOST, port=AppConfig.PORT)
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        traceback.print_exc()