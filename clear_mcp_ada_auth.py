#!/usr/bin/env python3
"""
MCP ADA認証情報をクリアするスクリプト
リダイレクトURI変更後にクライアント再登録を行うために使用
"""
import os
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_mcp_ada_credentials():
    """MCP ADA認証情報をクリア"""
    files_to_remove = [
        "mcp_ada_credentials.json",
        "mcp_ada_client.json"
    ]
    
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Removed: {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove {file_path}: {e}")
        else:
            logger.info(f"File not found: {file_path}")
    
    logger.info("MCP ADA credentials cleared. Client will re-register on next authentication attempt.")

if __name__ == "__main__":
    clear_mcp_ada_credentials()
