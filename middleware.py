"""
認証ミドルウェアの実装
"""
import os
import logging
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

def check_authentication(request: Request) -> bool:
    """セッションベースの認証状態をチェックする関数"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.session_auth import get_session_auth_manager
        
        session_manager = get_session_auth_manager()
        return session_manager.is_authenticated(request)
        
    except Exception as e:
        logger.error(f"Authentication check failed: {e}")
        return False

def require_authentication(request: Request):
    """認証を要求するデコレータ関数"""
    if not check_authentication(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def auth_middleware(request: Request, call_next):
    """
    認証ミドルウェア
    認証が必要なエンドポイントをチェック
    """
    # 認証が不要なパス
    public_paths = [
        "/auth/start",
        "/auth/callback", 
        "/auth/status",
        "/auth/logout",
        "/auth/mcp-ada/status",
        "/auth/mcp-ada/start",
        "/auth/mcp-ada/logout",
        "/auth/mcp-ada/callback",
        "/static",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/dev-ui/",
        "/list-apps",
        "/run",  # チャット機能のため一時的に追加
        "/apps/"  # セッション管理エンドポイント
    ]
    
    # 静的ファイルや認証が不要なパスの場合はスキップ
    if any(request.url.path.startswith(path) for path in public_paths):
        response = await call_next(request)
        return response
    
    # OPTIONS リクエストは認証不要
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response
    
    # APIエンドポイントでは基本的な認証状態をチェック
    # セッションベースの認証状態を確認
    if not check_authentication(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    response = await call_next(request)
    return response