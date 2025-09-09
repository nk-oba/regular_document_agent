"""
Debug Routes Module
Contains debug endpoints that should only be enabled in development environments.
"""
import logging
import sqlite3
import hashlib
from typing import Optional
from fastapi import Request, APIRouter
from config import AppConfig
from app_utils import generate_adk_user_id, get_db_connection
from error_handlers import handle_generic_error

logger = logging.getLogger(__name__)

# Create debug router
debug_router = APIRouter(prefix="/auth/debug", tags=["debug"])

def get_current_adk_user_id(request: Request = None) -> str:
    """ADK用の安定したユーザーIDを取得（デバッグ用ヘルパー）"""
    try:
        if not request:
            return "anonymous"
        
        from auth.session_auth import get_session_auth_manager
        
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        if user_info and user_info.get("email"):
            email = user_info["email"]
            adk_user_id = generate_adk_user_id(email)
            return adk_user_id
        
        return "anonymous"
        
    except Exception as e:
        logger.error(f"Failed to get ADK user ID: {e}")
        return "anonymous"

@debug_router.get("/user-info")
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
        return handle_generic_error(e, "debug user info", include_traceback=True)

@debug_router.get("/sessions-comparison")
async def debug_sessions_comparison(request: Request):
    """デバッグ用：セッション管理システムの比較"""
    try:
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
        expected_adk_user_id = generate_adk_user_id(email)
        adk_user_id_main = get_current_adk_user_id(request)
        
        # データベースの実際のデータを確認
        with get_db_connection() as conn:
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
        return handle_generic_error(e, "debug sessions comparison", include_traceback=True)

@debug_router.get("/artifact-paths")
async def debug_artifact_paths(request: Request):
    """Artifact保存パスのデバッグ情報を取得"""
    try:
        # セッションデータベースから現在の情報を取得
        with get_db_connection() as conn:
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
        
        # GCS情報の取得
        gcs_info = {
            "bucket_name": AppConfig.get_gcs_bucket_name(),
            "artifact_service_uri": AppConfig.ARTIFACT_URL
        }
        
        # 現在のログイン情報
        from auth.session_auth import get_session_auth_manager
        session_manager = get_session_auth_manager()
        user_info = session_manager.get_user_info(request)
        
        current_user_info = None
        if user_info:
            email = user_info.get("email")
            if email:
                adk_user_id = generate_adk_user_id(email)
                
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
        return handle_generic_error(e, "debug artifact paths", include_traceback=True)

@debug_router.get("/verify/consistency")
async def verify_user_id_consistency(request: Request):
    """ユーザーID生成の一貫性を検証"""
    try:
        from auth.session_auth import get_session_auth_manager
        from auth.unified_session_manager import get_unified_session_manager
        from auth.session_sync_manager import get_session_sync_manager
        from middleware import get_user_id_for_adk
        
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
        expected = generate_adk_user_id(email)
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
        return handle_generic_error(e, "verify user ID consistency", include_traceback=True)

def include_debug_routes(app):
    """Add debug routes to the main FastAPI app if DEBUG is enabled."""
    if AppConfig.DEBUG:
        app.include_router(debug_router)
        logger.info("Debug routes enabled")
    else:
        logger.info("Debug routes disabled (not in debug mode)")
        
    return app