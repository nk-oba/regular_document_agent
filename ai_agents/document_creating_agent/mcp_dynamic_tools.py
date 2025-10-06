"""
MCPサーバーから実際のツール定義を取得して、
ADK互換の関数として動的に生成する
"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def create_mcp_ada_dynamic_tools(tool_context=None) -> List[callable]:
    """
    MCP ADAサーバーから利用可能なツール一覧を取得し、
    ADK互換の関数として動的生成
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        List[callable]: 動的生成されたADK互換のMCPツール関数のリスト
    """
    dynamic_tools = []
    
    try:
        # セッション情報からユーザーIDを取得
        if tool_context:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        else:
            # フォールバック: 既知の認証ファイルから認証済みユーザーを探す
            user_id = _find_authenticated_user_id()
            
        # MCP ADAから利用可能なツール一覧を取得（OAuth2自動更新対応）
        available_tools = _fetch_mcp_tools_list(user_id, tool_context)
        
        if not available_tools:
            logger.info("No MCP ADA tools available")
            return []
        
        # 各MCPツールに対してADK互換の関数を動的生成
        for tool_def in available_tools:
            try:
                adk_function = _create_adk_function_from_mcp_tool(tool_def, user_id)
                if adk_function:
                    dynamic_tools.append(adk_function)
                    
            except Exception as tool_error:
                logger.warning(f"Failed to create ADK function for MCP tool {tool_def.get('name', 'unknown')}: {tool_error}")
        
        logger.info(f"Successfully created {len(dynamic_tools)} dynamic MCP ADA tools")
        return dynamic_tools
        
    except Exception as e:
        logger.error(f"Failed to create MCP ADA dynamic tools: {e}")
        return []


def _find_authenticated_user_id() -> str:
    """
    OAuth2Authファイルから認証済みGoogle User IDを検出

    Returns:
        str: 認証済みGoogle User ID、見つからない場合は"default"
    """
    try:
        import os
        import json
        import time
        from pathlib import Path

        # MCP ADA認証ディレクトリをチェック
        auth_dir = Path("auth_storage/mcp_ada_auth")

        if not auth_dir.exists():
            return "default"

        current_time = time.time()

        # 有効なOAuth2Authファイルを探す
        for oauth2_file in auth_dir.glob("mcp_ada_oauth2_auth_*.json"):
            try:
                with open(oauth2_file, 'r') as f:
                    oauth2_data = json.load(f)

                # トークンの有効期限をチェック（期限切れでもrefresh_tokenがあればOK）
                has_valid_token = oauth2_data.get('expires_at', 0) > current_time
                has_refresh_token = bool(oauth2_data.get('refresh_token'))

                if has_valid_token or has_refresh_token:
                    # ファイル名からGoogle User IDを抽出
                    # mcp_ada_oauth2_auth_{google_user_id}.json -> {google_user_id}
                    user_id = oauth2_file.stem.replace('mcp_ada_oauth2_auth_', '')
                    logger.info(f"Found authenticated Google User ID from OAuth2Auth file: {user_id}")
                    return user_id

            except Exception as file_error:
                logger.debug(f"Failed to check OAuth2Auth file {oauth2_file}: {file_error}")
                continue

        logger.info("No valid MCP ADA OAuth2Auth found")
        return "default"

    except Exception as e:
        logger.warning(f"Failed to find authenticated Google User ID: {e}")
        return "default"


def _fetch_mcp_tools_list(user_id: str, tool_context=None) -> Optional[List[Dict]]:
    """
    MCP ADAサーバーからツール一覧を取得（OAuth2自動更新対応）

    Args:
        user_id: Google User ID
        tool_context: ADK tool context（自動トークン更新に使用）

    Returns:
        Optional[List[Dict]]: MCPツール定義のリスト
    """
    try:
        # OAuth2自動更新機能を使用してトークンを取得
        from google.adk.auth import OAuth2Auth
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleAuthRequest
        import time
        import json
        import os

        # OAuth2Authファイルから読み込み
        oauth2_file = f"auth_storage/mcp_ada_auth/mcp_ada_oauth2_auth_{user_id}.json"

        if not os.path.exists(oauth2_file):
            logger.warning(f"No OAuth2Auth file found for user {user_id}")
            return None

        with open(oauth2_file, 'r') as f:
            oauth2_data = json.load(f)

        oauth2_auth = OAuth2Auth(**oauth2_data)

        # トークンの有効期限チェックと自動更新
        if oauth2_auth.expires_at and time.time() >= oauth2_auth.expires_at:
            logger.info("MCP ADA token expired, refreshing...")

            if not oauth2_auth.refresh_token:
                logger.error("No refresh token available")
                return None

            # トークン更新
            creds = Credentials(
                token=oauth2_auth.access_token,
                refresh_token=oauth2_auth.refresh_token,
                token_uri="https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token",
                client_id=oauth2_auth.client_id,
                client_secret=oauth2_auth.client_secret
            )

            creds.refresh(GoogleAuthRequest())

            # OAuth2Authを更新
            oauth2_auth.access_token = creds.token
            oauth2_auth.expires_at = int(creds.expiry.timestamp()) if creds.expiry else None

            # ファイルに保存
            with open(oauth2_file, 'w') as f:
                json.dump(oauth2_auth.model_dump(), f, indent=2)

            logger.info("✓ Token refreshed for MCP tools list fetch")

        access_token = oauth2_auth.access_token

        if not access_token:
            logger.warning(f"No valid access token for user {user_id}")
            return None
            
        # MCPサーバーに対してMCPプロトコルフローを実行
        import requests
        import re
        
        mcp_server_url = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev"
        
        # 1. MCP初期化リクエスト（セッションIDなし）
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "clientInfo": {
                    "name": "document_creating_agent",
                    "version": "1.0.0"
                }
            }
        }
        
        response = requests.post(
            f"{mcp_server_url}/mcp",
            headers=init_headers,
            json=init_request,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"MCP initialize failed: {response.status_code} - {response.text}")
            return None
            
        # セッションIDをレスポンスヘッダーから取得
        session_id = response.headers.get('mcp-session-id')
        if not session_id:
            logger.error("No session ID returned from MCP server")
            return None
            
        logger.info(f"MCP session initialized: {session_id}")
        
        # 2. tools/listリクエスト（セッションID付き）
        session_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": session_id
        }
        
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        
        response = requests.post(
            f"{mcp_server_url}/mcp",
            headers=session_headers,
            json=tools_request,
            timeout=30
        )
        
        if response.status_code == 200:
            # Server-Sent Eventsフォーマットの応答を解析
            response_text = response.text.strip()
            
            # SSE形式から実際のJSONを抽出
            # "data: {...}" 行を探す
            data_match = re.search(r'data:\s*({.*})', response_text)
            if data_match:
                import json
                data = json.loads(data_match.group(1))
                
                if "result" in data and "tools" in data["result"]:
                    tools_list = data["result"]["tools"]
                    logger.info(f"Retrieved {len(tools_list)} tools from MCP ADA server")
                    return tools_list
                else:
                    logger.warning(f"Unexpected MCP response format: {data}")
                    return None
            else:
                logger.error(f"Failed to parse SSE response: {response_text[:200]}...")
                return None
        else:
            logger.warning(f"Failed to fetch MCP tools: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching MCP tools list: {e}")
        return None


def _create_adk_function_from_mcp_tool(tool_def: Dict, user_id: str) -> Optional[callable]:
    """
    MCPツール定義からADK互換の関数を動的生成
    
    Args:
        tool_def: MCPツール定義
        user_id: ユーザーID
        
    Returns:
        Optional[callable]: 生成されたADK互換関数
    """
    try:
        tool_name = tool_def.get('name')
        tool_description = tool_def.get('description', '')
        input_schema = tool_def.get('inputSchema', {})
        
        if not tool_name:
            logger.warning("Tool definition missing name")
            return None
        
        # 動的に関数を生成
        async def dynamic_mcp_function(tool_context=None, **kwargs):
            """
            動的生成されたMCPツール呼び出し関数（OAuth2自動更新対応）
            """
            try:
                # OAuth2自動更新機能を使用してトークンを取得
                from google.adk.auth import OAuth2Auth
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request as GoogleAuthRequest
                import time
                import json
                import os

                # OAuth2Authファイルから読み込み
                oauth2_file = f"auth_storage/mcp_ada_auth/mcp_ada_oauth2_auth_{user_id}.json"

                if not os.path.exists(oauth2_file):
                    return f"❌ 認証エラー: {tool_name}の実行に必要な認証情報がありません（ファイルなし）"

                with open(oauth2_file, 'r') as f:
                    oauth2_data = json.load(f)

                oauth2_auth = OAuth2Auth(**oauth2_data)

                # トークンの有効期限チェックと自動更新
                if oauth2_auth.expires_at and time.time() >= oauth2_auth.expires_at:
                    logger.info(f"Token expired for {tool_name}, refreshing...")

                    if not oauth2_auth.refresh_token:
                        return f"❌ 認証エラー: リフレッシュトークンがありません"

                    # トークン更新
                    creds = Credentials(
                        token=oauth2_auth.access_token,
                        refresh_token=oauth2_auth.refresh_token,
                        token_uri="https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token",
                        client_id=oauth2_auth.client_id,
                        client_secret=oauth2_auth.client_secret
                    )

                    creds.refresh(GoogleAuthRequest())

                    # OAuth2Authを更新
                    oauth2_auth.access_token = creds.token
                    oauth2_auth.expires_at = int(creds.expiry.timestamp()) if creds.expiry else None

                    # ファイルに保存
                    with open(oauth2_file, 'w') as f:
                        json.dump(oauth2_auth.model_dump(), f, indent=2)

                    logger.info(f"✓ Token refreshed for {tool_name}")

                access_token = oauth2_auth.access_token

                if not access_token:
                    return f"❌ 認証エラー: {tool_name}の実行に必要な認証情報がありません"
                
                # MCPサーバーでセッションを初期化してツールを実行
                import requests
                import re
                import json
                
                mcp_server_url = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev"
                
                # 1. MCP初期化リクエスト
                init_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
                
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "clientInfo": {
                            "name": "document_creating_agent",
                            "version": "1.0.0"
                        }
                    }
                }
                
                response = requests.post(
                    f"{mcp_server_url}/mcp",
                    headers=init_headers,
                    json=init_request,
                    timeout=30
                )
                
                if response.status_code != 200:
                    return f"❌ MCP初期化エラー: {response.status_code} - {response.text}"
                
                # セッションIDを取得
                session_id = response.headers.get('mcp-session-id')
                if not session_id:
                    return f"❌ セッションID取得エラー"
                
                # 2. ツール実行リクエスト
                session_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "Mcp-Session-Id": session_id
                }
                
                tool_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": kwargs
                    }
                }
                
                response = requests.post(
                    f"{mcp_server_url}/mcp",
                    headers=session_headers,
                    json=tool_request,
                    timeout=60
                )
                
                if response.status_code == 200:
                    # Server-Sent Eventsフォーマットの応答を解析
                    response_text = response.text.strip()
                    
                    # SSE形式から実際のJSONを抽出
                    data_match = re.search(r'data:\s*({.*})', response_text)
                    if data_match:
                        data = json.loads(data_match.group(1))
                        logger.info(f"Successfully executed MCP tool: {tool_name}")
                        
                        # 結果をフォーマットして返す
                        if "result" in data:
                            result = data["result"]
                            if isinstance(result, dict) and "content" in result:
                                content = result["content"]
                                if content and len(content) > 0:
                                    return content[0].get("text", str(result))
                                else:
                                    return str(result)
                            else:
                                return str(result)
                        elif "error" in data:
                            return f"❌ MCPツールエラー: {data['error'].get('message', str(data['error']))}"
                        else:
                            return str(data)
                    else:
                        return f"❌ SSE応答解析エラー: {response_text[:200]}..."
                else:
                    error_msg = f"❌ MCPツール実行エラー: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return error_msg
                    
            except Exception as e:
                error_msg = f"❌ {tool_name}の実行中にエラーが発生しました: {str(e)}"
                logger.error(error_msg)
                return error_msg
        
        # 関数名と説明を設定
        dynamic_mcp_function.__name__ = f"mcp_{tool_name.replace('-', '_')}"
        dynamic_mcp_function.__doc__ = f"{tool_description}\n\nMCP ADAツール: {tool_name}"
        
        # 関数にメタデータを追加
        dynamic_mcp_function._mcp_tool_name = tool_name
        dynamic_mcp_function._mcp_tool_schema = input_schema
        
        logger.info(f"Created dynamic function for MCP tool: {tool_name}")
        return dynamic_mcp_function
        
    except Exception as e:
        logger.error(f"Failed to create function for tool {tool_def.get('name', 'unknown')}: {e}")
        return None