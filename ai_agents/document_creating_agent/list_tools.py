"""
利用可能なツールを一覧表示する機能
"""
import logging

logger = logging.getLogger(__name__)

async def list_tools(tool_context) -> str:
    """
    現在利用可能なツールを一覧表示
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        str: ツール一覧の説明
    """
    try:
        tools_list = """
🔧 **利用可能なツール一覧**

📊 **レポート生成ツール**:
- `generate_sample_csv_report`: サンプル広告レポートをCSV形式で生成
- `generate_monthly_performance_csv`: 月次パフォーマンスレポートをCSV生成
- `generate_sample_report_artifact`: JSON/TXT/HTML形式でレポート生成

🔐 **MCP ADA認証ツール**:
- `authenticate_mcp_server_tool`: MCP ADA認証を実行（セッションから自動取得）
- `make_mcp_authenticated_request_tool`: 認証付きAPIリクエスト実行
- `check_mcp_auth_status_tool`: 認証状態を確認

📋 **補助ツール**:
- `list_tools`: このツール一覧を表示

💡 **使用方法**:
- MCP ADA利用時はセッション情報からユーザーIDが自動取得されます
- 認証が済んでいる場合、改めて認証情報を入力する必要はありません
- エラーが発生した場合のみ、手動でuser_idを指定してください

🚀 **MCP ADA利用例**:
```
MCP ADAで広告データを取得してください
```
上記のように指示すると、自動的に認証済みユーザーでMCP ADAサーバーにアクセスします。
        """
        
        return tools_list.strip()
        
    except Exception as e:
        logger.error(f"Failed to list tools: {e}")
        return f"❌ ツール一覧の取得に失敗しました: {str(e)}"