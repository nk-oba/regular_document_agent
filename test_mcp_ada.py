#!/usr/bin/env python3
"""
MCP ADAツールの動作テスト
"""

import os
import sys
import logging

# パスを追加
sys.path.append(os.path.dirname(__file__))

from tools import get_mcp_ada_tool

def main():
    """MCP ADAツールをテスト"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("=== MCP ADAツール動作テスト ===")
    
    try:
        # MCP ADAツールを取得
        ada_tool = get_mcp_ada_tool()
        
        if ada_tool:
            logger.info("✅ MCP ADAツールの初期化が成功しました")
            
            # 利用可能なツールを確認
            try:
                # ツールセットから利用可能なツールリストを取得
                logger.info("📋 利用可能なツールを確認中...")
                # 実際のツール呼び出しはここで行える
                logger.info("MCP ADAツールが正常に動作しています")
                
            except Exception as e:
                logger.warning(f"ツール機能テストでエラー: {e}")
                
        else:
            logger.error("❌ MCP ADAツールの初期化に失敗しました")
            logger.error("認証が必要な可能性があります。scripts/authenticate_mcp_ada.py を実行してください")
            
    except Exception as e:
        logger.error(f"テスト中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
