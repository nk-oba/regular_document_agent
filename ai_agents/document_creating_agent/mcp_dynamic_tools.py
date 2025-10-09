"""
MCPサーバーから実際のツール定義を取得して、
ADK互換の関数として動的に生成する
"""
import logging
import json
import inspect
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Ensure DEBUG level is enabled

# MCPFunctionToolは使用せず、直接関数をツールとして登録する
# ADKのFunctionToolが自動的にFunctionDeclarationを生成するため、
# カスタムFunctionDeclarationを使う方法では動作しない可能性がある


def create_mcp_ada_dynamic_tools(tool_context=None) -> List[callable]:
    """
    MCP ADAサーバーから利用可能なツール一覧を取得し、
    FunctionDeclarationとして動的生成（description付き）

    Args:
        tool_context: ADK tool context

    Returns:
        List[callable]: 動的生成されたMCPツールのリスト
    """
    logger.info("[MCP ADA] === Starting MCP ADA dynamic tools creation ===")
    logger.debug(f"[MCP ADA] tool_context provided: {tool_context is not None}")

    dynamic_tools = []

    try:
        # セッション情報からユーザーIDを取得
        if tool_context:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
            logger.info(f"[MCP ADA] Retrieved user_id from session: {user_id}")
        else:
            # フォールバック: 既知の認証ファイルから認証済みユーザーを探す
            user_id = _find_authenticated_user_id()
            logger.info(f"[MCP ADA] Retrieved user_id from auth files: {user_id}")

        # MCP ADAから利用可能なツール一覧を取得(OAuth2自動更新対応)
        logger.info(f"[MCP ADA] Fetching tools list for user: {user_id}")
        available_tools = _fetch_mcp_tools_list(user_id, tool_context)

        if not available_tools:
            logger.warning("[MCP ADA] No MCP ADA tools available")
            return []

        logger.info(f"[MCP ADA] Found {len(available_tools)} tools to create")
        
        # 各MCPツールに対してFunctionDeclarationと実行関数を作成
        for idx, tool_def in enumerate(available_tools, 1):
            tool_name = tool_def.get('name', 'unknown')
            try:
                logger.debug(f"[MCP ADA] Creating tool {idx}/{len(available_tools)}: {tool_name}")
                
                # 1. FunctionDeclarationを作成（description付き）
                func_decl = _build_function_declaration_from_mcp(tool_def, user_id)
                if not func_decl:
                    logger.warning(f"[MCP ADA] Failed to create FunctionDeclaration for: {tool_name}")
                    continue
                
                # 2. 実行用の関数を作成
                executor_func = _create_adk_function_from_mcp_tool(tool_def, user_id)
                if not executor_func:
                    logger.warning(f"[MCP ADA] Failed to create executor function for: {tool_name}")
                    continue
                
                # 3. 関数を直接追加（ADKが自動的にFunctionDeclarationを生成）
                # 注: カスタムFunctionDeclarationは使用できないが、
                # docstringとtype annotationsからADKが自動生成する
                dynamic_tools.append(executor_func)
                logger.debug(f"[MCP ADA] ✓ Successfully created tool: {tool_name}")

            except Exception as tool_error:
                import traceback
                logger.warning(f"[MCP ADA] ✗ Failed to create tool {tool_name}: {tool_error}")
                logger.debug(f"[MCP ADA] Exception: {traceback.format_exc()}")

        logger.info(f"[MCP ADA] === Successfully created {len(dynamic_tools)}/{len(available_tools)} dynamic MCP ADA tools ===")
        return dynamic_tools

    except Exception as e:
        import traceback
        logger.error(f"[MCP ADA] Failed to create MCP ADA dynamic tools: {e}")
        logger.debug(f"[MCP ADA] Exception: {traceback.format_exc()}")
        return []


def _find_authenticated_user_id() -> str:
    """
    OAuth2Authファイルから認証済みGoogle User IDを検出

    Returns:
        str: 認証済みGoogle User ID、見つからない場合は"default"
    """
    try:
        import os
        import json as json_module
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
                    oauth2_data = json_module.load(f)

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
        import json as json_module
        import os

        # OAuth2Authファイルから読み込み
        oauth2_file = f"auth_storage/mcp_ada_auth/mcp_ada_oauth2_auth_{user_id}.json"

        if not os.path.exists(oauth2_file):
            logger.warning(f"No OAuth2Auth file found for user {user_id}")
            return None

        with open(oauth2_file, 'r') as f:
            oauth2_data = json_module.load(f)

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
                json_module.dump(oauth2_auth.model_dump(), f, indent=2)

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
            response.encoding = 'utf-8'
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
            # UTF-8エンコーディングを明示的に指定して文字化けを防ぐ
            response.encoding = 'utf-8'
            response_text = response.text.strip()

            # SSE形式から実際のJSONを抽出
            # "data: {...}" 行を探す
            data_match = re.search(r'data:\s*({.*})', response_text)
            if data_match:
                data = json_module.loads(data_match.group(1))

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
            response.encoding = 'utf-8'
            logger.warning(f"Failed to fetch MCP tools: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching MCP tools list: {e}")
        return None


def _build_function_declaration_from_mcp(tool_def: Dict, user_id: str) -> Optional['types.FunctionDeclaration']:
    """
    MCPツール定義からGoogle Genai FunctionDeclarationを直接作成
    
    Args:
        tool_def: MCPツール定義
        user_id: ユーザーID
        
    Returns:
        Optional[FunctionDeclaration]: 生成されたFunctionDeclaration
    """
    try:
        from google.genai import types
        
        tool_name = tool_def.get('name')
        tool_description = tool_def.get('description', '')
        input_schema = tool_def.get('inputSchema', {})
        
        if not tool_name:
            logger.warning("Tool definition missing name")
            return None
        
        # パラメータスキーマを構築
        properties = {}
        required_params = input_schema.get('required', [])
        
        # JSON SchemaからGoogle Genai Schemaに変換
        def convert_to_genai_schema(param_name: str, param_def: Dict) -> types.Schema:
            """JSON SchemaプロパティをGenai Schemaに変換"""
            param_type = param_def.get('type', 'string')
            description = param_def.get('description', '')
            
            # Type mapping
            type_mapping = {
                'string': types.Type.STRING,
                'number': types.Type.NUMBER,
                'integer': types.Type.INTEGER,
                'boolean': types.Type.BOOLEAN,
                'array': types.Type.ARRAY,
                'object': types.Type.OBJECT,
            }
            
            genai_type = type_mapping.get(param_type, types.Type.STRING)
            
            # array型の場合、itemsも変換
            if param_type == 'array':
                items = param_def.get('items', {})
                item_type = items.get('type', 'string')
                
                return types.Schema(
                    type=genai_type,
                    description=description,
                    items=types.Schema(
                        type=type_mapping.get(item_type, types.Type.STRING)
                    )
                )
            
            # object型の場合
            elif param_type == 'object':
                obj_properties = {}
                for sub_name, sub_def in param_def.get('properties', {}).items():
                    obj_properties[sub_name] = convert_to_genai_schema(sub_name, sub_def)
                
                return types.Schema(
                    type=genai_type,
                    description=description,
                    properties=obj_properties
                )
            
            # 基本型
            else:
                return types.Schema(
                    type=genai_type,
                    description=description
                )
        
        # 各パラメータを変換
        for param_name, param_def in input_schema.get('properties', {}).items():
            properties[param_name] = convert_to_genai_schema(param_name, param_def)
        
        # FunctionDeclarationを作成
        parameters_schema = types.Schema(
            type=types.Type.OBJECT,
            properties=properties,
            required=required_params
        )
        
        func_decl = types.FunctionDeclaration(
            name=tool_name.replace('-', '_'),  # プレフィックスなしで元のツール名を使用
            description=tool_description,
            parameters=parameters_schema
        )
        
        logger.info(f"[MCP ADA] Created FunctionDeclaration for: {tool_name}")
        logger.debug(f"[MCP ADA] FunctionDeclaration has {len(properties)} parameters with descriptions")
        
        return func_decl
        
    except Exception as e:
        logger.error(f"Failed to create FunctionDeclaration for tool {tool_def.get('name', 'unknown')}: {e}")
        import traceback
        logger.debug(f"Exception: {traceback.format_exc()}")
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
        import inspect
        from typing import Optional, Any

        tool_name = tool_def.get('name')
        tool_description = tool_def.get('description', '')
        input_schema = tool_def.get('inputSchema', {})

        if not tool_name:
            logger.warning("Tool definition missing name")
            return None

        # 実際の実装を行う内部関数（クロージャで変数をキャプチャ）
        async def _execute_mcp_tool(**actual_params):
            """
            動的生成されたMCPツール呼び出し関数（OAuth2自動更新対応）
            """
            logger.info(f"[MCP ADA] ========================================")
            logger.info(f"[MCP ADA] Tool invocation started: {tool_name}")
            logger.info(f"[MCP ADA] ========================================")

            # tool_contextを除外したパラメータを抽出
            tool_context = actual_params.pop('tool_context', None)
            kwargs = {k: v for k, v in actual_params.items() if v is not None}

            logger.info(f"[MCP ADA] === Tool Call Parameters ===")
            logger.info(f"[MCP ADA] Tool name: {tool_name}")
            logger.info(f"[MCP ADA] Received parameters: {kwargs}")
            logger.info(f"[MCP ADA] Tool context provided: {tool_context is not None}")

            try:
                # OAuth2自動更新機能を使用してトークンを取得
                from google.adk.auth import OAuth2Auth
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request as GoogleAuthRequest
                import time
                import json as json_module
                import os

                # OAuth2Authファイルから読み込み
                oauth2_file = f"auth_storage/mcp_ada_auth/mcp_ada_oauth2_auth_{user_id}.json"
                logger.debug(f"[MCP ADA] Looking for OAuth2 file: {oauth2_file}")

                if not os.path.exists(oauth2_file):
                    error_msg = f"❌ 認証エラー: {tool_name}の実行に必要な認証情報がありません（ファイルなし）"
                    logger.error(f"[MCP ADA] {error_msg}")
                    return error_msg

                logger.debug(f"[MCP ADA] Reading OAuth2 credentials from file")
                with open(oauth2_file, 'r') as f:
                    oauth2_data = json_module.load(f)

                oauth2_auth = OAuth2Auth(**oauth2_data)
                logger.debug(f"[MCP ADA] OAuth2 auth loaded, expires_at: {oauth2_auth.expires_at}")

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
                        json_module.dump(oauth2_auth.model_dump(), f, indent=2)

                    logger.info(f"✓ Token refreshed for {tool_name}")

                access_token = oauth2_auth.access_token

                if not access_token:
                    return f"❌ 認証エラー: {tool_name}の実行に必要な認証情報がありません"
                
                # MCPサーバーでセッションを初期化してツールを実行
                import requests
                import re

                mcp_server_url = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev"
                logger.info(f"[MCP ADA] Starting MCP session for tool: {tool_name}")

                # 1. MCP初期化リクエスト
                init_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
                logger.debug(f"[MCP ADA] Init headers prepared (token length: {len(access_token)})")
                
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
                
                logger.debug(f"[MCP ADA] Sending initialization request to {mcp_server_url}/mcp")
                response = requests.post(
                    f"{mcp_server_url}/mcp",
                    headers=init_headers,
                    json=init_request,
                    timeout=30
                )

                logger.debug(f"[MCP ADA] Init response: {response.status_code}")

                if response.status_code != 200:
                    response.encoding = 'utf-8'
                    error_msg = f"❌ MCP初期化エラー: {response.status_code} - {response.text}"
                    logger.error(f"[MCP ADA] {error_msg}")
                    return error_msg

                # セッションIDを取得
                session_id = response.headers.get('mcp-session-id')
                logger.debug(f"[MCP ADA] Session ID from headers: {session_id}")

                if not session_id:
                    error_msg = f"❌ セッションID取得エラー"
                    logger.error(f"[MCP ADA] {error_msg}")
                    logger.debug(f"[MCP ADA] Response headers: {dict(response.headers)}")
                    return error_msg

                logger.info(f"[MCP ADA] Session initialized: {session_id}")
                
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

                logger.info(f"[MCP ADA] Tool request: {json_module.dumps(tool_request, indent=2)}")

                # レポート取得は時間がかかる可能性があるため、タイムアウトを延長
                timeout_seconds = 900 if tool_name == "ada_get_report" else 60
                logger.info(f"[MCP ADA] Executing tool with timeout: {timeout_seconds}s")

                response = requests.post(
                    f"{mcp_server_url}/mcp",
                    headers=session_headers,
                    json=tool_request,
                    timeout=timeout_seconds
                )

                if response.status_code == 200:
                    # Server-Sent Eventsフォーマットの応答を解析
                    response.encoding = 'utf-8'
                    response_text = response.text.strip()
                    
                    # SSE形式から実際のJSONを抽出
                    data_match = re.search(r'data:\s*({.*})', response_text)
                    if data_match:
                        data = json_module.loads(data_match.group(1))
                        logger.info(f"[MCP ADA] Successfully executed MCP tool: {tool_name}")

                        # 結果をフォーマットして返す
                        if "result" in data:
                            result = data["result"]
                            logger.debug(f"[MCP ADA] Tool result type: {type(result)}")
                            logger.debug(f"[MCP ADA] Tool result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
                            logger.debug(f"[MCP ADA] Tool result: {result}")

                            if isinstance(result, dict) and "content" in result:
                                content = result["content"]
                                logger.debug(f"[MCP ADA] Result content length: {len(content) if content else 0}")
                                if content and len(content) > 0:
                                    final_result = content[0].get("text", str(result))
                                    logger.info(f"[MCP ADA] Returning text content (length: {len(final_result)})")
                                    return final_result
                                else:
                                    logger.warning(f"[MCP ADA] Result content is empty")
                                    return str(result)
                            else:
                                logger.info(f"[MCP ADA] Returning raw result")
                                return str(result)
                        elif "error" in data:
                            error_detail = data['error']
                            logger.error(f"[MCP ADA] Tool returned error: {error_detail}")
                            return f"❌ MCPツールエラー: {error_detail.get('message', str(error_detail))}"
                        else:
                            logger.warning(f"[MCP ADA] Unexpected response format: {data}")
                            return str(data)
                    else:
                        return f"❌ SSE応答解析エラー: {response_text[:200]}..."
                else:
                    response.encoding = 'utf-8'
                    error_msg = f"❌ MCPツール実行エラー: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return error_msg
                    
            except Exception as e:
                import traceback
                error_msg = f"❌ {tool_name}の実行中にエラーが発生しました: {str(e)}"
                logger.error(f"[MCP ADA] {error_msg}")
                logger.debug(f"[MCP ADA] Exception traceback: {traceback.format_exc()}")
                return error_msg

        # スキーマからパラメータ定義を構築
        # Pydantic Fieldを使用してパラメータの説明を保持
        param_names = ["tool_context"]
        param_types = {}  # Will store the actual type annotations
        pydantic_fields = {}  # Will store (type, Field) tuples for create_model

        # Build list of parameter names (without types for now)
        if input_schema and "properties" in input_schema:
            required_params = input_schema.get("required", [])

            # JSON SchemaのtypeをPython型オブジェクトに変換（array型の詳細情報も含む）
            from typing import List, Dict as TypingDict, Union, Any
            from pydantic import Field

            def get_python_type_from_schema(param_def: Dict) -> type:
                """JSON SchemaからPython型を取得（array型のitemsも考慮）"""
                param_type_str = param_def.get("type", "string")

                if param_type_str == "array":
                    # array型の場合、itemsから要素の型を取得
                    items = param_def.get("items", {})
                    item_type_str = items.get("type", "string")

                    # items型のマッピング
                    item_type_mapping = {
                        "string": str,
                        "number": float,
                        "integer": int,
                        "boolean": bool,
                        "object": dict
                    }
                    item_type = item_type_mapping.get(item_type_str, str)
                    return List[item_type]
                elif param_type_str == "object":
                    # object型の場合、properties があればより詳細な型を指定可能だが、
                    # シンプルにDict[str, Any]として扱う
                    return TypingDict[str, Any]
                else:
                    # 基本型のマッピング
                    type_mapping = {
                        "string": str,
                        "number": float,
                        "integer": int,
                        "boolean": bool,
                    }
                    return type_mapping.get(param_type_str, str)

            for param_name, param_def in input_schema["properties"].items():
                param_names.append(param_name)
                python_type = get_python_type_from_schema(param_def)
                description = param_def.get("description", "")

                # Pydantic用の(type, Field)タプルを作成
                # Optional型を使用
                pydantic_fields[param_name] = (
                    Union[python_type, None],
                    Field(default=None, description=description)
                )

                # __annotations__用の型（Fieldなし）
                param_types[param_name] = Union[python_type, None]

            # array型のパラメータにitemsが欠落している場合は補完
            for param_name, param_def in input_schema["properties"].items():
                if param_def.get("type") == "array" and "items" not in param_def:
                    logger.warning(f"[MCP ADA] Parameter '{param_name}' is array type but missing 'items', adding default")
                    param_def["items"] = {"type": "string"}  # デフォルトでstring配列として扱う

        # Create simple parameter list (name=None for all params)
        params_str = ", ".join([f"{p}=None" for p in param_names])
        logger.debug(f"[MCP ADA] Generated function parameters (without types): {params_str}")

        # パラメータの説明をdocstringに含める
        param_docs = []
        if input_schema and "properties" in input_schema:
            for param_name, param_def in input_schema["properties"].items():
                desc = param_def.get("description", "")
                if desc:
                    param_docs.append(f"        {param_name}: {desc}")

        docstring_content = f'''{tool_description}

    MCP ADAツール: {tool_name}

    Args:
{chr(10).join(param_docs) if param_docs else "        No parameters"}
'''

        # exec()を使ってラッパー関数を動的生成（型アノテーションなし）
        func_code = f'''
async def dynamic_mcp_function({params_str}):
    """{docstring_content}    """
    # パラメータのみを抽出（モジュールやその他のローカル変数を除外）
    _params = {{{', '.join([f"'{p}': {p}" for p in param_names])}}}
    return await _execute_mcp_tool(**_params)
'''
        logger.debug(f"[MCP ADA] Generated function code:\n{func_code}")

        # Execute to create the function
        func_namespace = {'_execute_mcp_tool': _execute_mcp_tool}
        exec(func_code, func_namespace)
        dynamic_mcp_function = func_namespace['dynamic_mcp_function']

        # Manually set __annotations__ with actual type objects
        dynamic_mcp_function.__annotations__ = param_types
        logger.debug(f"[MCP ADA] Set annotations: {dynamic_mcp_function.__annotations__}")

        # Pydantic Fieldの情報を関数に追加
        # これによりADKがパラメータの説明を取得できる
        dynamic_mcp_function.__pydantic_fields__ = pydantic_fields

        # 関数名を設定
        dynamic_mcp_function.__name__ = f"mcp_{tool_name.replace('-', '_')}"

        # 関数にメタデータを追加
        dynamic_mcp_function._mcp_tool_name = tool_name
        dynamic_mcp_function._mcp_tool_schema = input_schema

        logger.info(f"[MCP ADA] Created dynamic function for MCP tool: {tool_name}")
        logger.debug(f"[MCP ADA] Tool schema: {json.dumps(input_schema, indent=2)}")
        logger.debug(f"[MCP ADA] Function signature: {inspect.signature(dynamic_mcp_function)}")
        return dynamic_mcp_function
        
    except Exception as e:
        logger.error(f"Failed to create function for tool {tool_def.get('name', 'unknown')}: {e}")
        return None