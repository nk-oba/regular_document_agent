"""
Artifact保存時のユーザーID管理ヘルパー関数
セッション管理システムと統合したArtifact保存用のユーザー情報取得
"""
import logging
import hashlib
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def get_adk_stable_user_id_from_email(email: str) -> str:
    """emailからADK用の安定したユーザーID（16文字のハッシュ）を生成
    
    Args:
        email: ユーザーのメールアドレス
        
    Returns:
        16文字のハッシュ化されたユーザーID
    """
    if not email:
        return "anonymous"
    
    normalized_email = email.strip().lower()
    hash_object = hashlib.sha256(normalized_email.encode('utf-8'))
    return hash_object.hexdigest()[:16]

def get_artifact_user_info(tool_context) -> Dict[str, Any]:
    """Artifact保存用のユーザー情報を取得
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        ユーザー情報辞書 {user_id, session_id, email, is_authenticated}
    """
    try:
        # 1. InvocationContextからセッション情報を取得
        session_id = None
        invocation_id = None
        
        if hasattr(tool_context, 'invocation_context'):
            invocation_ctx = tool_context.invocation_context
            
            # 利用可能な属性を全て確認
            logger.debug(f"InvocationContext attributes: {dir(invocation_ctx)}")
            
            # invocation_idをセッションIDとして使用
            if hasattr(invocation_ctx, 'invocation_id'):
                invocation_id = invocation_ctx.invocation_id
                session_id = invocation_id
                logger.info(f"Found invocation_id: {invocation_id}")
            
            # その他の可能性のある属性をチェック
            for attr in ['session_id', 'conversation_id', 'session', 'id']:
                if hasattr(invocation_ctx, attr):
                    value = getattr(invocation_ctx, attr)
                    if value and not session_id:
                        session_id = str(value)
                        logger.info(f"Found {attr}: {value}")
        
        # 2. ADKが実際に使用するセッション情報を確認
        # ADKはsave_artifactの際に内部的にユーザーIDとセッションIDを決定する
        # そのため、実際に保存される時の情報を予測する必要がある
        
        # 3. SQLiteデータベースから現在のアクティブセッションを取得
        try:
            import sqlite3
            import os
            
            # セッションデータベースのパス
            session_db_path = "sessions.db"
            if os.path.exists(session_db_path):
                conn = sqlite3.connect(session_db_path)
                cursor = conn.cursor()
                
                # invocation_idに対応するセッションがあるかチェック
                if session_id:
                    cursor.execute("""
                        SELECT user_id FROM sessions 
                        WHERE id = ? AND app_name = 'document_creating_agent'
                        LIMIT 1
                    """, (session_id,))
                    
                    result = cursor.fetchone()
                    if result:
                        db_user_id = result[0]
                        logger.info(f"Found user_id for session {session_id}: {db_user_id}")
                        
                        # email形式の場合はADK stable user IDに変換
                        if isinstance(db_user_id, str) and '@' in db_user_id:
                            adk_user_id = get_adk_stable_user_id_from_email(db_user_id)
                            logger.info(f"Converted email to ADK user ID: {db_user_id[:5]}... -> {adk_user_id}")
                            
                            conn.close()
                            return {
                                'user_id': adk_user_id,
                                'session_id': session_id,
                                'email': db_user_id,
                                'is_authenticated': True,
                                'source': 'database_session_matched'
                            }
                        else:
                            # 既にADK user ID形式の場合
                            conn.close()
                            return {
                                'user_id': db_user_id,
                                'session_id': session_id,
                                'email': None,
                                'is_authenticated': True,
                                'source': 'database_session_matched'
                            }
                
                # セッション特定ができない場合は最近のアクティブセッション
                cursor.execute("""
                    SELECT user_id, id FROM sessions 
                    WHERE app_name = 'document_creating_agent'
                    ORDER BY update_time DESC 
                    LIMIT 1
                """)
                
                result = cursor.fetchone()
                if result:
                    db_user_id, db_session_id = result
                    logger.info(f"Found recent session: user_id={db_user_id}, session_id={db_session_id}")
                    
                    # sessionIdが取得できていない場合は最新のものを使用
                    if not session_id:
                        session_id = db_session_id
                        logger.info(f"Using recent session_id: {session_id}")
                    
                    # email形式の場合はADK stable user IDに変換
                    if isinstance(db_user_id, str) and '@' in db_user_id:
                        adk_user_id = get_adk_stable_user_id_from_email(db_user_id)
                        logger.info(f"Converted email to ADK user ID: {db_user_id[:5]}... -> {adk_user_id}")
                        
                        conn.close()
                        return {
                            'user_id': adk_user_id,
                            'session_id': session_id or 'unknown',
                            'email': db_user_id,
                            'is_authenticated': True,
                            'source': 'database_recent_converted'
                        }
                    else:
                        # 既にADK user ID形式の場合
                        conn.close()
                        return {
                            'user_id': db_user_id,
                            'session_id': session_id or 'unknown',
                            'email': None,
                            'is_authenticated': True,
                            'source': 'database_recent_adk_id'
                        }
                
                conn.close()
                
        except Exception as db_error:
            logger.warning(f"Failed to get user info from database: {db_error}")
        
        # 3. ファイルベースのセッション管理から取得を試行
        try:
            from pathlib import Path
            import json
            import time
            
            sessions_dir = Path("auth_storage/sessions/auth_sessions")
            if sessions_dir.exists():
                # 最新のアクティブセッションファイルを探す
                current_time = time.time()
                
                for session_file in sessions_dir.glob("*.json"):
                    try:
                        with open(session_file, 'r') as f:
                            session_data = json.load(f)
                            
                            # 有効期限チェック
                            if session_data.get('expires_at', 0) > current_time:
                                user_info = session_data.get('user_info', {})
                                email = user_info.get('email')
                                
                                if email:
                                    adk_user_id = get_adk_stable_user_id_from_email(email)
                                    logger.info(f"Found valid session with email: {email[:5]}...")
                                    
                                    return {
                                        'user_id': adk_user_id,
                                        'session_id': session_id or invocation_id or session_file.stem,
                                        'email': email,
                                        'is_authenticated': True,
                                        'source': 'file_session'
                                    }
                    except Exception as file_error:
                        logger.debug(f"Failed to read session file {session_file}: {file_error}")
                        continue
                        
        except Exception as session_error:
            logger.warning(f"Failed to get user info from session files: {session_error}")
        
        # 4. フォールバック: anonymousユーザーとして処理
        logger.warning("All user info methods failed, using anonymous fallback")
        return {
            'user_id': 'anonymous',
            'session_id': session_id or invocation_id or 'unknown',
            'email': None,
            'is_authenticated': False,
            'source': 'fallback'
        }
        
    except Exception as e:
        logger.error(f"Critical error in get_artifact_user_info: {e}")
        return {
            'user_id': 'anonymous',
            'session_id': 'error',
            'email': None,
            'is_authenticated': False,
            'source': 'error'
        }

def generate_download_urls(app_name: str, user_info: Dict[str, Any], filename: str, version: int) -> Dict[str, str]:
    """ダウンロードURL群を生成
    
    Args:
        app_name: アプリケーション名
        user_info: ユーザー情報辞書
        filename: ファイル名
        version: バージョン番号
        
    Returns:
        各種ダウンロードURLの辞書
    """
    user_id = user_info['user_id']
    session_id = user_info['session_id']
    
    # 基本的なダウンロードURL
    download_url = f"http://localhost:8000/download/artifact/{app_name}/{user_id}/{session_id}/{filename}"
    if version:
        download_url += f"?version={version}"
    
    # API形式のURL
    api_download_url = f"http://localhost:8000/apps/{app_name}/users/{user_id}/{session_id}/artifacts/{filename}"
    if version:
        api_download_url += f"?version={version}"
    
    # invocation_id基準のURL（フォールバック）
    invocation_download_url = f"http://localhost:8000/download/artifact/by-invocation/{session_id}/{filename}"
    if version:
        invocation_download_url += f"?version={version}"
    
    return {
        'primary': download_url,
        'api': api_download_url,
        'invocation': invocation_download_url
    }

async def save_artifact_with_proper_user_id(tool_context, filename: str, artifact, return_detailed_info: bool = True) -> Dict[str, Any]:
    """適切なユーザーID管理でArtifactを保存
    
    Args:
        tool_context: ADK tool context
        filename: ファイル名
        artifact: Artifactオブジェクト
        return_detailed_info: 詳細情報を返すかどうか
        
    Returns:
        保存結果とユーザー情報
    """
    try:
        # 1. 保存前にユーザー情報を取得（保存パスの予測のため）
        user_info_before = get_artifact_user_info(tool_context)
        logger.info(f"User info before save: {user_info_before}")
        
        # 2. Artifactを保存（ADKが内部的にユーザーIDを管理）
        version = await tool_context.save_artifact(
            filename=filename,
            artifact=artifact
        )
        
        logger.info(f"Artifact saved successfully: {filename} (version {version})")
        
        # 3. 保存後にもう一度ユーザー情報を確認（実際の保存パスの確認のため）
        user_info_after = get_artifact_user_info(tool_context)
        logger.info(f"User info after save: {user_info_after}")
        
        # 4. ADKの実際の保存動作を考慮した情報を使用
        # ADKは以下の優先順位でuser_idを決定する可能性が高い:
        # 1. tool_contextから直接取得できるuser_id
        # 2. invocation_contextのuser_id
        # 3. 何らかのフォールバック値
        
        # InvocationContextを詳しく調査
        if hasattr(tool_context, 'invocation_context'):
            invocation_ctx = tool_context.invocation_context
            logger.info(f"Detailed invocation context inspection:")
            
            # 全ての属性をログ出力
            for attr_name in dir(invocation_ctx):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(invocation_ctx, attr_name)
                        if not callable(attr_value):
                            logger.info(f"  {attr_name}: {attr_value}")
                    except Exception as attr_error:
                        logger.debug(f"  {attr_name}: <error: {attr_error}>")
        
        # 5. 最終的なユーザー情報の決定
        # 保存後の情報を優先するが、不明な場合は保存前の情報も参考にする
        final_user_info = user_info_after
        
        # session_idが不明な場合の追加対策
        if final_user_info['session_id'] == 'unknown':
            # より広範囲でセッション情報を探す
            alternative_session_id = _find_alternative_session_id(tool_context)
            if alternative_session_id:
                final_user_info['session_id'] = alternative_session_id
                logger.info(f"Found alternative session_id: {alternative_session_id}")
        
        # 6. 基本的な結果を構築
        result = {
            'success': True,
            'filename': filename,
            'version': version,
            'user_id': final_user_info['user_id'],
            'session_id': final_user_info['session_id'],
            'is_authenticated': final_user_info['is_authenticated']
        }
        
        # 7. 詳細情報が要求された場合
        if return_detailed_info:
            app_name = "document_creating_agent"
            download_urls = generate_download_urls(app_name, final_user_info, filename, version)
            
            result.update({
                'email': final_user_info.get('email'),
                'source': final_user_info.get('source'),
                'download_urls': download_urls,
                'app_name': app_name,
                'debug_info': {
                    'user_info_before': user_info_before,
                    'user_info_after': user_info_after
                }
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to save artifact with proper user ID: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            'success': False,
            'error': str(e),
            'filename': filename,
            'user_id': 'unknown',
            'session_id': 'unknown',
            'is_authenticated': False
        }

def _find_alternative_session_id(tool_context) -> Optional[str]:
    """代替のセッションID取得を試行"""
    try:
        # tool_contextの詳細な属性チェック
        if hasattr(tool_context, 'session_id'):
            return str(tool_context.session_id)
        
        if hasattr(tool_context, 'session'):
            return str(tool_context.session)
        
        # Invocation Contextのより詳細なチェック
        if hasattr(tool_context, 'invocation_context'):
            ctx = tool_context.invocation_context
            
            # 一般的な候補をチェック
            for attr_name in ['invocation_id', 'session_id', 'conversation_id', 'id', 'request_id']:
                if hasattr(ctx, attr_name):
                    value = getattr(ctx, attr_name)
                    if value and isinstance(value, str):
                        logger.info(f"Alternative session_id found via {attr_name}: {value}")
                        return value
        
        # データベースから最新のセッションIDを取得
        import sqlite3
        import os
        
        session_db_path = "sessions.db"
        if os.path.exists(session_db_path):
            conn = sqlite3.connect(session_db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id FROM sessions 
                WHERE app_name = 'document_creating_agent'
                ORDER BY update_time DESC 
                LIMIT 1
            """)
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                session_id = result[0]
                logger.info(f"Alternative session_id from database: {session_id}")
                return session_id
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to find alternative session_id: {e}")
        return None

def format_download_section(save_result: Dict[str, Any]) -> str:
    """ダウンロードセクションのフォーマット済みテキストを生成
    
    Args:
        save_result: save_artifact_with_proper_user_id の戻り値
        
    Returns:
        フォーマット済みのダウンロードセクション文字列
    """
    if not save_result.get('success'):
        return f"❌ ファイル保存エラー: {save_result.get('error', 'Unknown error')}"
    
    filename = save_result['filename']
    version = save_result['version']
    user_info = f"User: {save_result['user_id'][:8]}..." if save_result['user_id'] != 'anonymous' else "User: Anonymous"
    auth_status = "✅ 認証済み" if save_result['is_authenticated'] else "⚠️ 未認証"
    
    download_section = f"""📥 **ダウンロード情報**:
**ファイル**: {filename} (Version {version})
**ユーザー**: {user_info} {auth_status}

**ダウンロード方法**:
1. **ダイレクトダウンロード**: [🗂️ {filename} をダウンロード]({save_result['download_urls']['primary']}) ⭐推奨
2. **チャットUI**: 下に表示されるダウンロードボタンをクリック
3. **API形式**: [JSON形式でアクセス]({save_result['download_urls']['api']})"""

    # デバッグ情報（認証されていない場合）
    if not save_result['is_authenticated']:
        download_section += f"""

**📋 デバッグ情報**:
- ユーザーID取得方法: {save_result.get('source', 'unknown')}
- セッションID: {save_result['session_id']}
- フォールバックURL: [invocation基準]({save_result['download_urls']['invocation']})"""

    return download_section
