#!/usr/bin/env python3
"""
MCP ADA サーバー認証スクリプト
独自のOAuth 2.0認可サーバーを使用してトークンを取得
"""

import os
import sys
import logging

# パスを追加してauth モジュールをインポート可能にする
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from auth.mcp_ada_auth import get_mcp_ada_auth_manager

def main():
    """MCP ADA認証を実行"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("=== MCP ADA サーバー認証開始 ===")
    logger.info("認証エンドポイント: https://mcp-server-ad-analyzer.adt-c1a.workers.dev/authorize")
    logger.info("トークンエンドポイント: https://mcp-server-ad-analyzer.adt-c1a.workers.dev/token")
    logger.info("必要なスコープ: mcp:reports, mcp:properties")
    print()
    
    try:
        # MCP ADA認証マネージャーを取得
        auth_manager = get_mcp_ada_auth_manager()
        
        # 既存のトークンをチェック
        existing_token = auth_manager.get_access_token()
        if existing_token:
            logger.info("✅ 既存のMCP ADAトークンが見つかりました")
            print(f"アクセストークン: {existing_token[:20]}...")
            
            # トークンを強制的に更新するかユーザーに確認
            response = input("\n新しいトークンを取得しますか？ (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                logger.info("既存のトークンを使用します")
                return existing_token
        
        # 新しい認証フローを開始
        logger.info("🔐 MCP ADA認証フローを開始します...")
        print("ブラウザで認証ページが開きます。認証を完了してください。")
        print()
        
        access_token = auth_manager.get_access_token(force_refresh=True)
        
        if access_token:
            logger.info("✅ MCP ADA認証が成功しました！")
            print(f"アクセストークン: {access_token[:20]}...")
            print()
            logger.info("認証情報は mcp_ada_credentials.json に保存されました")
            
            # 認証情報のテスト
            logger.info("🧪 認証情報をテストしています...")
            test_auth(access_token)
            
        else:
            logger.error("❌ MCP ADA認証に失敗しました")
            return None
            
    except KeyboardInterrupt:
        logger.info("認証がキャンセルされました")
        return None
    except Exception as e:
        logger.error(f"認証中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_auth(access_token):
    """認証情報をテスト"""
    import requests
    
    logger = logging.getLogger(__name__)
    
    try:
        # MCP ADAサーバーのヘルスチェックエンドポイントをテスト
        test_url = "https://mcp-server-ad-analyzer.adt-c1a.workers.dev/mcp"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info("✅ MCP ADAサーバーとの接続テストが成功しました")
        elif response.status_code == 401:
            logger.warning("⚠️  認証エラー: トークンが無効の可能性があります")
        else:
            logger.warning(f"⚠️  予期しないレスポンス: {response.status_code}")
            
    except Exception as e:
        logger.warning(f"⚠️  接続テストでエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
