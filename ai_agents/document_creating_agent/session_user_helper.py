"""
セッション情報からユーザーIDを取得するヘルパー関数
MCP ADA認証でセッション済みユーザー情報を自動取得
"""
import sys
import os
import logging

# パスを追加してsharedモジュールをインポート可能にする
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)

def get_user_id_from_session(tool_context) -> str:
    """
    セッション情報から現在のログインユーザーIDを取得（Google User IDを優先）

    Args:
        tool_context: ADK tool context

    Returns:
        str: Google User ID、なければデフォルト
    """
    try:
        # 共通のユーザー情報取得ヘルパーを使用
        from shared.utils.artifact_user_helper import get_artifact_user_info

        user_info = get_artifact_user_info(tool_context)

        # Google User IDが取得できている場合は、それを最優先で使用
        if user_info.get('id'):
            google_user_id = user_info['id']
            logger.info(f"Found Google User ID from session: {google_user_id}")
            return google_user_id

        # ADK user IDが取得できている場合はそれを使用
        elif user_info.get('user_id') and user_info['user_id'] != 'anonymous':
            logger.info(f"Found user_id from session: {user_info['user_id']}")
            return user_info['user_id']

        # 認証されていない場合はデフォルト
        else:
            logger.warning("No authenticated user found in session, using default")
            return "default"

    except Exception as e:
        logger.error(f"Failed to get user_id from session: {e}")
        return "default"


def get_session_aware_mcp_ada_auth_manager(tool_context):
    """
    セッション情報を考慮したMCP ADA認証マネージャーを取得
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        MCPADAAuthManager: セッションユーザー用の認証マネージャー
    """
    try:
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        
        # セッションからユーザーIDを取得
        user_id = get_user_id_from_session(tool_context)
        
        # そのユーザーID用のMCP ADA認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager(user_id)
        
        logger.info(f"Created MCP ADA auth manager for user: {user_id}")
        return auth_manager
        
    except Exception as e:
        logger.error(f"Failed to create session-aware MCP ADA auth manager: {e}")
        # フォールバック: デフォルトのマネージャー
        from shared.auth.mcp_ada_auth import get_mcp_ada_auth_manager
        return get_mcp_ada_auth_manager("default")