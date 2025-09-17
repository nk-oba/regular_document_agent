import logging
import os
import sys
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, Union
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from google.genai import types

# パスを追加してauth モジュールをインポート可能にする
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def get_google_access_token():
    """Google認証トークンを安全に取得"""
    try:
        from shared.auth.google_auth import get_google_access_token as _get_token
        return _get_token()
    except ImportError as e:
        logging.error(f"Google auth module not available: {e}")
        return None
    except Exception as e:
        logging.error(f"Failed to get Google access token: {e}")
        return None


def get_tools():
    """MCPツールを安全に読み込み（遅延初期化）"""
    tools = []

    # Artifact生成ツールを追加
    tools.extend([
        generate_sample_csv_report,
        # authenticate_mcp_server_tool,
        # make_mcp_authenticated_request_tool,
        # check_mcp_auth_status_tool
    ])

    
    # TODO 動的認証に組み替える
    mcp_toolset = None
    try:
        from shared.auth.mcp_ada_auth import get_mcp_ada_access_token
        access_token = get_mcp_ada_access_token(user_id="usr0302483@login.gmo-ap.jp")
        
        if access_token:
            mcp_toolset = MCPToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url="https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
            )
            logging.info("MCP ADA toolset initialized with valid access token")
        else:
            logging.warning("No valid MCP ADA access token available. MCP tools will not be initialized.")
            
    except Exception as e:
        logging.error(f"Failed to initialize MCP ADA toolset: {e}")

    # MCP ADA toolsetをtoolsに追加（認証済みの場合のみ）
    if mcp_toolset:
        tools.append(mcp_toolset)
        logging.info("MCP ADA toolset added to tools")

    # # list_tools関数をインポートして追加
    # try:
    #     from list_tools import list_tools
    #     tools.append(list_tools)
    # except ImportError as e:
    #     logging.warning(f"Failed to import list_tools: {e}")
    
    # MCPツールの初期化をスキップしてサーバー起動を優先
    logging.info("MCP tools will be initialized on first use (lazy loading)")
    logging.info(f"Added {len(tools)} tools (including MCP toolset if authenticated)")
    
    # # MCP ADAが認証済みの場合、サーバーから実際のツールを動的に取得
    # try:
    #     from mcp_dynamic_tools import create_mcp_ada_dynamic_tools
    #     dynamic_mcp_tools = create_mcp_ada_dynamic_tools()
        
    #     if dynamic_mcp_tools:
    #         tools.extend(dynamic_mcp_tools)
    #         logging.info(f"Added {len(dynamic_mcp_tools)} dynamic MCP ADA tools to available tools")
    #     else:
    #         logging.info("No MCP ADA tools available or not authenticated")
    # except Exception as e:
    #     logging.warning(f"Failed to load dynamic MCP ADA tools: {e}")
    
    return tools


def get_mcp_ada_tool():
    """MCP ADAツールを安全に初期化"""
    try:
        URL = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp"
        
        # Google OAuth2.0でアクセストークンを取得
        access_token = get_google_access_token()
        
        if not access_token:
            logging.warning("Failed to get Google access token. Please run authentication first.")
            return None
        
        logging.debug(f"Initializing MCP ADA tool: {URL}")
        logging.debug(f"Using access token: {access_token[:20]}..." if access_token else "No access token")
        
        # デバッグ: ヘッダー情報をログ出力
        headers = {"Authorization": f"Bearer {access_token}"}
        logging.debug(f"Request headers: {headers}")
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers=headers,
            )
        )
        
        logging.info("MCP ADA tool initialized successfully")
        return toolset
        
    except Exception as e:
        logging.error(f"Failed to initialize MCP ADA tool: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def get_mcp_powerpoint_tool():
    """MCP PowerPointツールを安全に初期化"""
    try:
        logging.debug("Initializing MCP PowerPoint tool")
        
        toolset = MCPToolset(
            connection_params=StdioServerParameters(
                command="npx",
                args=["-y", "@smithery/cli@latest", "run", "@GongRzhe/Office-PowerPoint-MCP-Server"],
            )
        )
        
        logging.info("MCP PowerPoint tool initialized successfully")
        return toolset
        
    except Exception as e:
        logging.error(f"Failed to initialize MCP PowerPoint tool: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def generate_sample_csv_report(tool_context):
    """
    サンプルCSVレポートを生成してダウンロード可能なArtifactとして保存する
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        str: 生成されたCSVファイルの情報
    """
    try:
        # テスト用のサンプルデータを生成
        sample_data = [
            ["Campaign ID", "Campaign Name", "Impressions", "Clicks", "CTR (%)", "Cost (JPY)", "CPC (JPY)", "Date"],
            ["12345", "夏セールキャンペーン", "125,000", "3,200", "2.56", "48,000", "15", "2024-08-15"],
            ["12346", "新商品発売記念", "89,500", "2,150", "2.40", "32,250", "15", "2024-08-16"],
            ["12347", "バックトゥスクール", "156,300", "4,890", "3.13", "73,350", "15", "2024-08-17"],
            ["12348", "週末限定セール", "203,100", "6,093", "3.00", "91,395", "15", "2024-08-18"],
            ["12349", "アウトレットクリアランス", "78,900", "1,578", "2.00", "23,670", "15", "2024-08-19"]
        ]
        
        # CSVデータをバイト形式で生成
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerows(sample_data)
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')  # BOM付きUTF-8でExcel対応
        
        # ADK Artifactとして作成
        csv_artifact = types.Part.from_bytes(
            data=csv_bytes,
            mime_type="text/csv"
        )
        
        # ファイル名にタイムスタンプを含める
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"advertising_campaign_report_{timestamp}.csv"
        
        # 新しいヘルパー関数を使用してArtifactを保存
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from shared.utils.artifact_user_helper import save_artifact_with_proper_user_id, format_download_section
        
        # Artifactを適切なユーザー管理で保存
        save_result = await save_artifact_with_proper_user_id(
            tool_context=tool_context,
            filename=filename,
            artifact=csv_artifact,
            return_detailed_info=True
        )
        
        if save_result['success']:
            logging.info(f"CSV report generated successfully: {filename} (version {save_result['version']})")
            # フォーマット済みダウンロードセクションを取得
            download_section = format_download_section(save_result)
            version = save_result['version']
        else:
            logging.error(f"Failed to save CSV artifact: {save_result.get('error')}")
            download_section = f"❌ ファイル保存エラー: {save_result.get('error', 'Unknown error')}"
            version = 0
        
        return f"""✅ CSVレポートが正常に生成されました！

📄 **ファイル名**: `{filename}`
📊 **データ**: 5件のサンプル広告キャンペーンデータ
🔢 **バージョン**: {version}
🕐 **生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{download_section}

📊 **含まれるデータ**:
- キャンペーンID、キャンペーン名
- インプレッション数、クリック数
- CTR（クリック率）、広告費用
- CPC（クリック単価）、実行日付

💡 このファイルはExcelで直接開いて分析可能です！
"""
        
    except Exception as e:
        error_msg = f"CSV生成中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg



# ==============================================================================
# MCP認証ツール統合
# ==============================================================================

async def authenticate_mcp_server_tool(
    tool_context,
    server_url: str,
    user_id: Optional[str] = None,
    scopes: Optional[list[str]] = None
):
    """
    MCP ADA準拠のOAuth 2.1認証を実行するツール
    
    Args:
        tool_context: ADK tool context
        server_url: 認証対象のMCPサーバーURL
        user_id: ユーザーID（未指定の場合はセッションから自動取得）
        scopes: 要求するスコープリスト（デフォルト: ["mcp:reports", "mcp:properties"]）
        
    Returns:
        str: 認証結果メッセージ
    """
    try:
        # セッション情報からユーザーIDを自動取得（user_idが未指定の場合）
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        
        # MCP認証ツールセットをインポート
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import authenticate_mcp_server_helper
        
        # MCP ADA専用スコープをデフォルトに設定
        if scopes is None:
            scopes = ["mcp:reports", "mcp:properties"]
        
        logging.info(f"Authenticating to MCP server: {server_url} (user: {user_id}, scopes: {scopes})")
        
        # MCP認証を実行
        result = await authenticate_mcp_server_helper(server_url, user_id, scopes)
        
        logging.info(f"MCP authentication completed for {server_url}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP認証ツールが利用できません: {e}\n\n💡 MCP認証フレームワークが正しくインストールされているか確認してください。"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ MCP認証中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


async def make_mcp_authenticated_request_tool(
    tool_context,
    server_url: str,
    method: str,
    path: str,
    user_id: Optional[str] = None,
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    query_params: Optional[dict] = None
):
    """
    MCP認証付きHTTPリクエストを実行するツール
    
    Args:
        tool_context: ADK tool context
        server_url: MCPサーバーURL
        method: HTTPメソッド（GET, POST, PUT, DELETE, PATCH）
        path: リクエストパス
        user_id: ユーザーID（未指定の場合はセッションから自動取得）
        headers: 追加のHTTPヘッダー
        json_data: JSONボディデータ
        query_params: クエリパラメータ
        
    Returns:
        str: リクエスト結果
    """
    try:
        # セッション情報からユーザーIDを自動取得（user_idが未指定の場合）
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        # MCP認証ツールセットをインポート
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import mcp_request_helper
        
        # パラメータの準備
        kwargs = {}
        if headers:
            kwargs["headers"] = headers
        if json_data:
            kwargs["json"] = json_data
        if query_params:
            kwargs["params"] = query_params
        
        logging.info(f"Making authenticated request: {method} {server_url}{path} (user: {user_id})")
        
        # MCP認証付きリクエストを実行
        result = await mcp_request_helper(
            server_url,
            method.upper(),
            path,
            user_id,
            **kwargs
        )
        
        logging.info(f"MCP request completed: {method} {server_url}{path}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP認証ツールが利用できません: {e}\n\n💡 MCP認証フレームワークが正しくインストールされているか確認してください。"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ MCP認証付きリクエスト中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg


async def check_mcp_auth_status_tool(
    tool_context,
    server_url: str,
    user_id: Optional[str] = None
):
    """
    MCP認証状態を確認するツール
    
    Args:
        tool_context: ADK tool context
        server_url: MCPサーバーURL
        user_id: ユーザーID（未指定の場合はセッションから自動取得）
        
    Returns:
        str: 認証状態情報
    """
    try:
        # セッション情報からユーザーIDを自動取得（user_idが未指定の場合）
        if user_id is None:
            from session_user_helper import get_user_id_from_session
            user_id = get_user_id_from_session(tool_context)
        # MCP認証ツールセットをインポート
        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from mcp_client.mcp_toolset import get_mcp_auth_toolset
        
        logging.info(f"Checking auth status for: {server_url} (user: {user_id})")
        
        # 認証状態をチェック
        auth_toolset = get_mcp_auth_toolset()
        status_result = await auth_toolset.check_status(server_url, user_id)
        
        # 結果をフォーマット
        if status_result.get("authenticated"):
            result = f"""✅ 認証状態確認完了

{status_result.get('result', '')}

💡 **状態**: 認証済み
🌐 **サーバー**: {server_url}
👤 **ユーザー**: {user_id}
"""
        else:
            result = f"""❌ 認証が必要です

🌐 **サーバー**: {server_url}
👤 **ユーザー**: {user_id}
🔐 **状態**: 未認証

💡 **次のステップ**: 
```
authenticate_mcp_server_tool("{server_url}", "{user_id}")
```
を実行して認証してください。

エラー詳細: {status_result.get('error', 'Unknown error')}
"""
        
        logging.info(f"Auth status check completed for {server_url}")
        return result
        
    except ImportError as e:
        error_msg = f"❌ MCP認証ツールが利用できません: {e}\n\n💡 MCP認証フレームワークが正しくインストールされているか確認してください。"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ MCP認証状態確認中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg
