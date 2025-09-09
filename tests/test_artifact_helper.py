#!/usr/bin/env python3
"""
Artifact保存ヘルパー関数のテストスクリプト
"""
import sys
import os
import asyncio
import logging
from unittest.mock import Mock, MagicMock

# ログ設定
logging.basicConfig(level=logging.INFO)

# パスを追加
sys.path.append(os.path.dirname(__file__))

async def test_artifact_helper():
    """Artifact保存ヘルパー関数のテスト"""
    try:
        from shared.utils.artifact_user_helper import (
            get_artifact_user_info, 
            save_artifact_with_proper_user_id,
            format_download_section,
            get_adk_stable_user_id_from_email
        )
        
        print("✅ ヘルパー関数のインポートが成功しました")
        
        # 1. ユーザーID生成のテスト
        test_email = "test@example.com"
        adk_user_id = get_adk_stable_user_id_from_email(test_email)
        print(f"📧 Email: {test_email}")
        print(f"🔑 ADK User ID: {adk_user_id}")
        print(f"📏 User ID Length: {len(adk_user_id)}")
        
        # 2. モックツールコンテキストの作成
        mock_tool_context = Mock()
        mock_invocation_context = Mock()
        mock_invocation_context.invocation_id = "test-invocation-123"
        mock_tool_context.invocation_context = mock_invocation_context
        
        # モックのsave_artifact関数
        async def mock_save_artifact(filename, artifact):
            print(f"📁 Mock saving artifact: {filename}")
            return 1  # version 1
        
        mock_tool_context.save_artifact = mock_save_artifact
        
        # 3. ユーザー情報取得のテスト
        user_info = get_artifact_user_info(mock_tool_context)
        print(f"👤 User Info: {user_info}")
        
        # 4. Artifactの作成（モック）
        mock_artifact = Mock()
        mock_artifact.inline_data = Mock()
        mock_artifact.inline_data.data = b"test,data\n1,2\n"
        mock_artifact.inline_data.mime_type = "text/csv"
        
        # 5. save_artifact_with_proper_user_id のテスト
        save_result = await save_artifact_with_proper_user_id(
            tool_context=mock_tool_context,
            filename="test_report.csv",
            artifact=mock_artifact,
            return_detailed_info=True
        )
        
        print(f"💾 Save Result: {save_result}")
        
        # 6. ダウンロードセクションのフォーマットテスト
        download_section = format_download_section(save_result)
        print(f"📥 Download Section Preview:")
        print(download_section[:200] + "...")
        
        print("\n✅ すべてのテストが正常に完了しました！")
        
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        print("utils/artifact_user_helper.py が見つからないか、依存関係に問題があります")
    except Exception as e:
        print(f"❌ テスト実行エラー: {e}")
        import traceback
        traceback.print_exc()

def test_user_id_consistency():
    """ユーザーID生成の一貫性テスト"""
    try:
        from shared.utils.artifact_user_helper import get_adk_stable_user_id_from_email
        
        test_cases = [
            "user@example.com",
            "User@Example.com",  # 大文字小文字
            " user@example.com ",  # 空白
            "test123@gmail.com",
            "complex.email+tag@domain.co.jp"
        ]
        
        print("\n🧪 ユーザーID生成の一貫性テスト:")
        for email in test_cases:
            user_id = get_adk_stable_user_id_from_email(email)
            print(f"  📧 {email!r} → 🔑 {user_id}")
        
        # 同じemailに対して一貫したIDが生成されることを確認
        email = "test@example.com"
        id1 = get_adk_stable_user_id_from_email(email)
        id2 = get_adk_stable_user_id_from_email(email)
        id3 = get_adk_stable_user_id_from_email(email.upper())  # 大文字版
        
        print(f"\n🔍 一貫性チェック:")
        print(f"  同じメール: {id1 == id2} ({'✅' if id1 == id2 else '❌'})")
        print(f"  大文字小文字違い: {id1 == id3} ({'✅' if id1 == id3 else '❌'})")
        
    except Exception as e:
        print(f"❌ 一貫性テストエラー: {e}")

if __name__ == "__main__":
    print("🚀 Artifact保存ヘルパー関数のテストを開始...")
    
    # 基本テスト
    asyncio.run(test_artifact_helper())
    
    # 一貫性テスト
    test_user_id_consistency()
    
    print("\n🏁 テスト完了")
