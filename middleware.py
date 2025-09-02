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

def check_authentication() -> bool:
    """認証状態をチェックする関数"""
    try:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from auth.google_auth import get_auth_manager
        
        auth_manager = get_auth_manager()
        token = auth_manager.get_access_token()
        
        return token is not None
        
    except Exception as e:
        logger.error(f"Authentication check failed: {e}")
        return False

def require_authentication():
    """認証を要求するデコレータ関数"""
    if not check_authentication():
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
        "/list-apps"
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
    # サーバー側の認証状態を確認（Google OAuth トークンが有効かどうか）
    if not check_authentication():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    response = await call_next(request)
    return response