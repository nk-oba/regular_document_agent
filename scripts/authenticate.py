#!/usr/bin/env python3
"""
Google OAuth認証を実行するスクリプト
MCP ADAツール使用前に実行してください
"""
import os
import sys

# パスを追加してagentsモジュールをインポート可能にする
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.google_auth import get_auth_manager

def main():
    print("Google OAuth2.0認証を開始します...")
    print("MCP ADAツールへのアクセスに必要な認証情報を取得します。")
    print()
    
    auth_manager = get_auth_manager()
    
    # 既存の認証情報をチェック
    existing_token = auth_manager.get_access_token()
    
    if existing_token:
        print("✓ 有効な認証情報が見つかりました。")
        print("新しい認証を実行する場合は、引数に --force を追加してください。")
        return
    
    # 強制リフレッシュが要求された場合
    force_refresh = '--force' in sys.argv
    
    # 認証フローを実行
    token = auth_manager.get_access_token(force_refresh=force_refresh)
    
    if token:
        print("\n✓ Google認証が完了しました。")
        print("MCP ADAツールを使用できます。")
    else:
        print("\n✗ 認証に失敗しました。")
        print("以下を確認してください:")
        print("1. client_secrets.json が正しく設定されている")
        print("2. 環境変数 GOOGLE_OAUTH_CLIENT_SECRETS が設定されている")
        print("3. Google Cloud Console でOAuth認証情報が設定されている")
        sys.exit(1)

if __name__ == "__main__":
    main()