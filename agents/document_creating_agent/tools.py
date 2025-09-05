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
        from auth.google_auth import get_google_access_token as _get_token
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
    
    # CSV生成ツールを追加
    tools.extend([
        generate_sample_csv_report,
        generate_monthly_performance_csv
    ])
    
    # MCPツールの初期化をスキップしてサーバー起動を優先
    logging.info("MCP tools will be initialized on first use (lazy loading)")
    logging.info(f"Added {len(tools)} CSV generation tools")
    
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
        
        # Artifactを保存
        version = await tool_context.save_artifact(
            filename=filename,
            artifact=csv_artifact
        )
        
        logging.info(f"CSV report generated successfully: {filename} (version {version})")
        
        return f"""CSVレポートが正常に生成されました！

📄 ファイル名: {filename}
📊 データ: 5件のサンプル広告キャンペーンデータ
🔢 バージョン: {version}

ダウンロード方法:
1. チャットインターフェースでダウンロードボタンをクリック
2. または 'load_artifact' ツールを使用してプログラム的にアクセス

含まれるデータ:
- キャンペーンID、名前
- インプレッション数、クリック数
- CTR、コスト、CPC
- 実行日付
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
        
        # Artifactを保存
        version = await tool_context.save_artifact(
            filename=filename,
            artifact=csv_artifact
        )
        
        logging.info(f"Monthly performance CSV generated: {filename} (version {version})")
        
        return f"""月次パフォーマンスレポートが生成されました！

📅 対象期間: {year}年{month}月
📄 ファイル名: {filename} 
📊 データ件数: {len(data)-1}件 (ヘッダー除く)
🔢 バージョン: {version}

レポート内容:
- 日別キャンペーンパフォーマンス
- デバイス別分析
- コンバージョン・CPA追跡
- 主要指標の詳細データ

このファイルはExcelで開くか、データ分析ツールでご利用いただけます。
"""
        
    except Exception as e:
        error_msg = f"月次レポート生成中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        return error_msg
