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
        generate_monthly_performance_csv,
        generate_sample_report_artifact,
        authenticate_mcp_server_tool,
        make_mcp_authenticated_request_tool,
        check_mcp_auth_status_tool
    ])
    
    # list_tools関数をインポートして追加
    try:
        from list_tools import list_tools
        tools.append(list_tools)
    except ImportError as e:
        logging.warning(f"Failed to import list_tools: {e}")
    
    # MCPツールの初期化をスキップしてサーバー起動を優先
    logging.info("MCP tools will be initialized on first use (lazy loading)")
    logging.info(f"Added {len(tools)} tools (including {3} MCP auth tools)")
    
    # 注意：実際のMCPツールの初期化は get_mcp_ada_tool_lazy() などで行う
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
        
        toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
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


async def generate_monthly_performance_csv(tool_context, year: Optional[int] = None, month: Optional[int] = None):
    """
    月次パフォーマンスレポートのCSVを生成
    
    Args:
        tool_context: ADK tool context
        year: レポート対象年 (デフォルト: 現在年)
        month: レポート対象月 (デフォルト: 先月)
        
    Returns:
        str: 生成されたCSVファイルの情報
    """
    try:
        # デフォルト値の設定
        if not year or not month:
            now = datetime.now()
            if not year:
                year = now.year
            if not month:
                # 先月を取得
                first_day_this_month = now.replace(day=1)
                last_month = first_day_this_month - timedelta(days=1)
                month = last_month.month
                if month == 12:
                    year -= 1
        
        # 月次データの生成（30日分）
        headers = ["Date", "Campaign", "Device", "Impressions", "Clicks", "CTR (%)", "Cost (JPY)", "Conversions", "CPA (JPY)"]
        data = [headers]
        
        campaigns = ["ブランド認知", "商品販売", "アプリダウンロード", "リードジェネレーション"]
        devices = ["Desktop", "Mobile", "Tablet"]
        
        import random
        random.seed(42)  # 再現可能な結果のため
        
        for day in range(1, 31):
            for campaign in campaigns[:2]:  # 主要キャンペーン2つに絞る
                device = random.choice(devices)
                impressions = random.randint(5000, 25000)
                clicks = random.randint(int(impressions * 0.01), int(impressions * 0.05))
                ctr = round((clicks / impressions) * 100, 2)
                cost = random.randint(10000, 50000)
                conversions = random.randint(5, 50)
                cpa = round(cost / conversions, 0) if conversions > 0 else 0
                
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                row = [date_str, campaign, device, impressions, clicks, ctr, cost, conversions, int(cpa)]
                data.append(row)
        
        # CSVデータをバイト形式で生成
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        csv_writer.writerows(data)
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')
        
        # ADK Artifactとして作成
        csv_artifact = types.Part.from_bytes(
            data=csv_bytes,
            mime_type="text/csv"
        )
        
        # ファイル名
        filename = f"monthly_performance_{year:04d}{month:02d}.csv"
        
        # 新しいヘルパー関数を使用してArtifactを保存
        from shared.utils.artifact_user_helper import save_artifact_with_proper_user_id, format_download_section
        
        # Artifactを適切なユーザー管理で保存
        save_result = await save_artifact_with_proper_user_id(
            tool_context=tool_context,
            filename=filename,
            artifact=csv_artifact,
            return_detailed_info=True
        )
        
        if save_result['success']:
            logging.info(f"Monthly performance CSV generated: {filename} (version {save_result['version']})")
            # フォーマット済みダウンロードセクションを取得
            download_section = format_download_section(save_result)
            version = save_result['version']
        else:
            logging.error(f"Failed to save monthly CSV artifact: {save_result.get('error')}")
            download_section = f"❌ ファイル保存エラー: {save_result.get('error', 'Unknown error')}"
            version = 0
        
        return f"""✅ 月次パフォーマンスレポートが生成されました！

📅 **対象期間**: {year}年{month}月
📄 **ファイル名**: `{filename}`
📊 **データ件数**: {len(data)-1}件（ヘッダー除く）
🔢 **バージョン**: {version}
🕐 **生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{download_section}

📈 **レポート内容**:
- 📊 日別キャンペーンパフォーマンス
- 📱 デバイス別分析（Desktop/Mobile/Tablet）
- 🎯 コンバージョン・CPA追跡
- 📋 主要指標の詳細データ

💼 **活用方法**:
- Excelでピボットテーブル分析
- Google Sheetsでグラフ作成
- BIツール（Tableau、Power BI）でダッシュボード構築
- Python/Rでの統計分析

🔍 月次トレンド分析やROI最適化にご活用ください！
"""
        
    except Exception as e:
        error_msg = f"月次レポート生成中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        return error_msg


async def generate_sample_report_artifact(tool_context, format_type: str = "json"):
    """
    サンプルレポートを任意の形式で生成（汎用Artifactデモ）
    
    Args:
        tool_context: ADK tool context
        format_type: 生成するファイル形式 ("json", "txt", "html")
        
    Returns:
        str: 生成されたファイルの情報
    """
    try:
        # サンプルデータ
        report_data = {
            "report_title": "広告キャンペーン分析レポート",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_campaigns": 5,
                "total_impressions": 750000,
                "total_clicks": 18500,
                "average_ctr": 2.47,
                "total_cost": 275000
            },
            "campaigns": [
                {"name": "夏セールキャンペーン", "impressions": 125000, "clicks": 3200, "cost": 48000},
                {"name": "新商品発売記念", "impressions": 89500, "clicks": 2150, "cost": 32250},
                {"name": "バックトゥスクール", "impressions": 156300, "clicks": 4890, "cost": 73350},
                {"name": "週末限定セール", "impressions": 203100, "clicks": 6093, "cost": 91395},
                {"name": "アウトレットクリアランス", "impressions": 78900, "clicks": 1578, "cost": 23670}
            ]
        }
        
        # 形式に応じてデータを変換
        if format_type.lower() == "json":
            import json
            file_data = json.dumps(report_data, ensure_ascii=False, indent=2).encode('utf-8')
            filename = f"campaign_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            mime_type = "application/json"
            
        elif format_type.lower() == "txt":
            text_content = f"""広告キャンペーン分析レポート
生成日時: {report_data['generated_at']}

サマリー:
- 総キャンペーン数: {report_data['summary']['total_campaigns']}
- 総インプレッション数: {report_data['summary']['total_impressions']:,}
- 総クリック数: {report_data['summary']['total_clicks']:,}
- 平均CTR: {report_data['summary']['average_ctr']}%
- 総コスト: {report_data['summary']['total_cost']:,}円

キャンペーン詳細:
"""
            for campaign in report_data['campaigns']:
                text_content += f"- {campaign['name']}: {campaign['impressions']:,}imp, {campaign['clicks']:,}click, {campaign['cost']:,}円\n"
            
            file_data = text_content.encode('utf-8')
            filename = f"campaign_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            mime_type = "text/plain"
            
        elif format_type.lower() == "html":
            html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>広告キャンペーン分析レポート</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .summary {{ background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>広告キャンペーン分析レポート</h1>
    <p><strong>生成日時:</strong> {report_data['generated_at']}</p>
    
    <div class="summary">
        <h2>サマリー</h2>
        <ul>
            <li>総キャンペーン数: {report_data['summary']['total_campaigns']}</li>
            <li>総インプレッション数: {report_data['summary']['total_impressions']:,}</li>
            <li>総クリック数: {report_data['summary']['total_clicks']:,}</li>
            <li>平均CTR: {report_data['summary']['average_ctr']}%</li>
            <li>総コスト: {report_data['summary']['total_cost']:,}円</li>
        </ul>
    </div>
    
    <h2>キャンペーン詳細</h2>
    <table>
        <thead>
            <tr>
                <th>キャンペーン名</th>
                <th>インプレッション数</th>
                <th>クリック数</th>
                <th>コスト</th>
            </tr>
        </thead>
        <tbody>"""
            for campaign in report_data['campaigns']:
                html_content += f"""
            <tr>
                <td>{campaign['name']}</td>
                <td>{campaign['impressions']:,}</td>
                <td>{campaign['clicks']:,}</td>
                <td>{campaign['cost']:,}円</td>
            </tr>"""
            
            html_content += """
        </tbody>
    </table>
</body>
</html>"""
            file_data = html_content.encode('utf-8')
            filename = f"campaign_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            mime_type = "text/html"
            
        else:
            return f"❌ サポートされていないファイル形式: {format_type}\nサポート形式: json, txt, html"
        
        # ADK Artifactとして作成
        artifact = types.Part.from_bytes(
            data=file_data,
            mime_type=mime_type
        )
        
        # 新しいヘルパー関数を使用してArtifactを保存
        from shared.utils.artifact_user_helper import save_artifact_with_proper_user_id, format_download_section
        
        # Artifactを適切なユーザー管理で保存
        save_result = await save_artifact_with_proper_user_id(
            tool_context=tool_context,
            filename=filename,
            artifact=artifact,
            return_detailed_info=True
        )
        
        if save_result['success']:
            logging.info(f"Generic artifact generated: {filename} (version {save_result['version']}, format: {format_type})")
            # フォーマット済みダウンロードセクションを取得
            download_section = format_download_section(save_result)
            version = save_result['version']
        else:
            logging.error(f"Failed to save generic artifact: {save_result.get('error')}")
            download_section = f"❌ ファイル保存エラー: {save_result.get('error', 'Unknown error')}"
            version = 0
        
        return f"""✅ {format_type.upper()}形式のレポートが生成されました！

📄 **ファイル名**: `{filename}`
📊 **形式**: {format_type.upper()}
🔢 **バージョン**: {version}
📦 **MIMEタイプ**: {mime_type}
🕐 **生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{download_section}

📈 **レポート内容**:
- 📊 キャンペーン分析データ
- 📋 サマリー統計情報
- 🎯 個別キャンペーン詳細

💼 **活用方法**:
- {format_type.upper()}ファイルとして保存・共有
- 他のツールで後処理
- アーカイブとして保管

🔧 この機能は汎用Artifactダウンロード機能のデモンストレーションです！
"""
        
    except Exception as e:
        error_msg = f"{format_type}レポート生成中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
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
