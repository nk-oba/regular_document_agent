"""
Authentication Routes Module
Contains all authentication-related endpoints including OAuth, session management, and MCP auth.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse

from shared.core.config import AppConfig
from shared.services.app_utils import generate_adk_user_id
from shared.services.error_handlers import handle_auth_error, handle_session_error, create_success_response
from shared.auth.google_auth import get_auth_manager
from shared.auth.session_auth import get_session_auth_manager
from shared.auth.session_sync_manager import get_session_sync_manager
from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
from shared.auth.unified_session_manager import get_unified_session_manager

logger = logging.getLogger(__name__)

# Create authentication router
auth_router = APIRouter(prefix="/auth", tags=["authentication"])

@auth_router.get("/callback")
async def oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    """Google OAuth2.0認証コールバック"""
    if error:
        return {"error": f"Authentication failed: {error}"}
    
    if not code:
        return {"error": "No authorization code provided"}
    
    try:
        logger.info(f"Processing OAuth callback with code: {code[:20]}...")
        
        # 認証コードをauth moduleに渡して処理
        
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
                if AppConfig.USE_UNIFIED_SESSION_MANAGEMENT:
                    # 統合セッション管理を使用（フォールバック付き）
                    try:
                        unified_manager = get_unified_session_manager()
                        unified_session = unified_manager.create_unified_session(user_data, credentials)
                        session_id = unified_session["login_session_id"]
                        adk_user_id = unified_session["adk_user_id"]
                        logger.info(f"Using unified session management")
                    except Exception as e:
                        logger.warning(f"Unified session failed, using sync manager: {e}")
                        # フォールバック: 従来のセッション同期管理
                        sync_manager = get_session_sync_manager()
                        session_id, adk_user_id = sync_manager.on_login(user_data, credentials)
                else:
                    # 従来のセッション同期管理を使用
                    sync_manager = get_session_sync_manager()
                    session_id, adk_user_id = sync_manager.on_login(user_data, credentials)
                
                # MCP用認証情報の保存
                try:
                    mcp_auth_manager = get_mcp_ada_auth_manager()
                    user_id = generate_adk_user_id(user_data["email"])
                    mcp_auth_manager.save_user_credentials(user_id, credentials)
                    logger.info(f"Credentials saved for MCP user: {user_id}")
                except Exception as mcp_error:
                    logger.warning(f"Failed to save MCP credentials: {mcp_error}")
                
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

@auth_router.get("/status")
async def auth_status(request: Request):
    """現在の認証ステータスを確認（セッションベース）"""
    try:
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

@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """認証情報をクリア（セッションベース）"""
    try:
        
        session_manager = get_session_auth_manager()
        sync_manager = get_session_sync_manager()
        
        session_id = session_manager.get_session_id_from_request(request)
        
        if session_id:
            # セッション同期管理でログアウト処理
            sync_manager.on_logout(session_id)
            logger.info(f"Session {session_id} logged out via sync manager")
        
        # セッションクッキーをクリア
        session_manager.clear_session_cookie(response)
        
        return {"success": True, "message": "Logged out successfully"}
        
    except Exception as e:
        return handle_auth_error(e, "logout")

@auth_router.get("/start")
async def start_oauth(request: Request):
    """Google OAuth認証を開始"""
    try:
        logger.info("OAuth start endpoint called")
        
        # セッションベースの認証状態をチェック
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info:
            logger.info(f"User already authenticated: {user_info.get('email', 'unknown')}")
            return {
                "success": True,
                "message": "Already authenticated",
                "authenticated": True
            }
        
        logger.info("Starting new OAuth flow")
        
        from google_auth_oauthlib.flow import Flow
        
        auth_manager = get_auth_manager()
        if not auth_manager.client_secrets_file:
            logger.error("OAuth client secrets not configured")
            return {"success": False, "error": "OAuth client secrets not configured"}
        
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
        
        logger.info(f"Generated OAuth URL: {auth_url[:100]}...")
        
        return create_success_response(
            "Please visit the auth_url to complete authentication",
            auth_url=auth_url
        )
        
    except Exception as e:
        logger.error(f"OAuth start error: {e}")
        return handle_auth_error(e, "OAuth start")

@auth_router.get("/google")
async def google_oauth_redirect(request: Request):
    """Google OAuth認証へのリダイレクト（フロントエンド互換性のため）"""
    try:
        logger.info("Google OAuth redirect endpoint called")
        
        # セッションベースの認証状態をチェック
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info:
            logger.info(f"User already authenticated: {user_info.get('email', 'unknown')}")
            # 既に認証済みの場合はフロントエンドにリダイレクト
            return RedirectResponse(url=AppConfig.FRONTEND_REDIRECT_URL, status_code=302)
        
        logger.info("Redirecting to Google OAuth")
        
        from google_auth_oauthlib.flow import Flow
        
        auth_manager = get_auth_manager()
        if not auth_manager.client_secrets_file:
            logger.error("OAuth client secrets not configured")
            return RedirectResponse(
                url=f"{AppConfig.FRONTEND_REDIRECT_URL}?error=oauth_not_configured", 
                status_code=302
            )
        
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
        
        logger.info(f"Redirecting to OAuth URL: {auth_url[:100]}...")
        
        # 直接OAuth URLにリダイレクト
        return RedirectResponse(url=auth_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Google OAuth redirect error: {e}")
        return RedirectResponse(
            url=f"{AppConfig.FRONTEND_REDIRECT_URL}?error=oauth_failed", 
            status_code=302
        )

# MCP ADA Authentication Endpoints
@auth_router.get("/mcp-ada/status")
async def mcp_ada_auth_status():
    """MCP ADA認証ステータスを確認（ユーザー共通）"""
    try:
        
        # MCP用のユーザーIDを取得（ユーザー共通）
        user_id = "shared_user"  # MCP ADAは共通ユーザー
        
        mcp_auth_manager = get_mcp_ada_auth_manager()
        is_authenticated = mcp_auth_manager.is_authenticated(user_id)
        
        if is_authenticated:
            auth_info = mcp_auth_manager.get_auth_info(user_id)
            return {
                "authenticated": True,
                "user_id": user_id,
                "auth_info": auth_info
            }
        else:
            return {
                "authenticated": False,
                "user_id": user_id,
                "auth_url": f"/auth/mcp-ada/authenticate?user_id={user_id}"
            }
            
    except Exception as e:
        return handle_auth_error(e, "MCP ADA auth status")

@auth_router.get("/mcp-ada/authenticate")
async def mcp_ada_authenticate(user_id: str = "shared_user"):
    """MCP ADA認証を開始"""
    try:
        
        mcp_auth_manager = get_mcp_ada_auth_manager()
        auth_url = mcp_auth_manager.get_authorization_url(user_id)
        
        return create_success_response(
            "Please visit the auth_url to complete MCP ADA authentication",
            auth_url=auth_url,
            user_id=user_id
        )
        
    except Exception as e:
        return handle_auth_error(e, "MCP ADA authenticate start")

@auth_router.get("/mcp-ada/callback")
async def mcp_ada_callback(request: Request):
    """MCP ADA認証コールバック"""
    try:
        
        # クエリパラメータから認証コードを取得
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        error = request.query_params.get('error')
        
        if error:
            return {"success": False, "error": f"MCP ADA authentication failed: {error}"}
        
        if not code:
            return {"success": False, "error": "No authorization code provided"}
        
        # stateからuser_idを復元（簡単な実装）
        user_id = state if state else "shared_user"
        
        mcp_auth_manager = get_mcp_ada_auth_manager()
        success = mcp_auth_manager.process_authorization_code(user_id, code)
        
        if success:
            # HTMLレスポンスでユーザーに成功を通知
            with open(AppConfig.MCP_ADA_CALLBACK_HTML, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            return HTMLResponse(content=html_content)
        else:
            return {"success": False, "error": "Failed to process MCP ADA authorization code"}
            
    except Exception as e:
        return handle_auth_error(e, "MCP ADA callback")

@auth_router.post("/mcp-ada/logout")
async def mcp_ada_logout(user_id: str = "shared_user"):
    """MCP ADA認証をクリア"""
    try:
        
        mcp_auth_manager = get_mcp_ada_auth_manager()
        mcp_auth_manager.clear_credentials(user_id)
        
        return create_success_response("MCP ADA credentials cleared successfully")
        
    except Exception as e:
        return handle_auth_error(e, "MCP ADA logout")

# Session Management Endpoints
@auth_router.get("/session/info")
async def get_session_info(request: Request):
    """現在のセッション情報を取得"""
    try:
        
        session_manager = get_session_auth_manager()
        sync_manager = get_session_sync_manager()
        
        session_id = session_manager.get_session_id_from_request(request)
        user_info = session_manager.get_user_info(request)
        
        if session_id:
            session_info = sync_manager.get_session_info(session_id)
            return {
                "session_id": session_id,
                "user_info": user_info,
                "session_info": session_info,
                "authenticated": user_info is not None
            }
        else:
            return {
                "authenticated": False,
                "message": "No active session"
            }
            
    except Exception as e:
        return handle_session_error(e, "get session info")

@auth_router.get("/sessions/list")
async def list_sessions(request: Request):
    """現在のユーザーのセッション一覧を取得"""
    try:
        
        session_manager = get_session_auth_manager()
        sync_manager = get_session_sync_manager()
        
        user_info = session_manager.get_user_info(request)
        if not user_info or not user_info.get("email"):
            return {"error": "Not authenticated", "sessions": []}
        
        email = user_info["email"]
        adk_user_id = generate_adk_user_id(email)
        
        sessions = sync_manager.get_user_sessions(adk_user_id)
        
        return {
            "user_id": adk_user_id,
            "email": email,
            "sessions": sessions
        }
        
    except Exception as e:
        return handle_session_error(e, "list sessions")

@auth_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """指定されたセッションを削除"""
    try:
        
        session_manager = get_session_auth_manager()
        sync_manager = get_session_sync_manager()
        
        user_info = session_manager.get_user_info(request)
        if not user_info:
            return {"error": "Not authenticated", "success": False}
        
        # セッション削除
        success = sync_manager.delete_session(session_id)
        
        if success:
            return create_success_response(f"Session {session_id} deleted successfully")
        else:
            return {"success": False, "error": "Failed to delete session"}
            
    except Exception as e:
        return handle_session_error(e, "delete session", session_id)

# Utility function to include auth routes
def include_auth_routes(app):
    """Add authentication routes to the main FastAPI app."""
    app.include_router(auth_router)
    logger.info("Authentication routes included")
    return app