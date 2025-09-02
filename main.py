import os
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import json
import asyncio
from typing import List
import logging
import re

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# agent engone parameters
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DB_URL = "sqlite:///./sessions.db"
ARTIFACT_URL = "gs://dev-datap-agent-bucket"
ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000", 
    "http://localhost:3000", 
    "http://127.0.0.1:8001", 
    "http://localhost:8001",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*"
]
SERVE_WEB_INTERFACE = True

load_dotenv()

# エージェントを安全にインポート
try:
    from document_creating_agent.agent import root_agent
    logger.info("Successfully imported root_agent")
except Exception as e:
    logger.error(f"Failed to import root_agent: {str(e)}")
    import traceback
    traceback.print_exc()
    root_agent = None

# FastAPIアプリケーションを安全に作成
try:
    # サービスアカウント認証が設定されている場合はGCSを使用
    google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if google_creds_path and os.path.exists(google_creds_path.replace("/app/", "/app/")):
        logger.info(f"Using GCS Artifact Service with credentials: {google_creds_path}")
        app: FastAPI = get_fast_api_app(
            agents_dir=AGENT_DIR,
            session_service_uri=SESSION_DB_URL,
            artifact_service_uri=ARTIFACT_URL,  # GCSを使用
            allow_origins=ALLOWED_ORIGINS,
            web=SERVE_WEB_INTERFACE
        )
    else:
        logger.info("Using InMemory Artifact Service (no GCS credentials found)")
        app: FastAPI = get_fast_api_app(
            agents_dir=AGENT_DIR,
            session_service_uri=SESSION_DB_URL,
            # artifact_service_uri=ARTIFACT_URL,  # InMemoryを使用
            allow_origins=ALLOWED_ORIGINS,
            web=SERVE_WEB_INTERFACE
        )
    logger.info("Successfully created FastAPI app")
except Exception as e:
    logger.error(f"Failed to create FastAPI app: {str(e)}")
    import traceback
    traceback.print_exc()
    raise


# CORS設定を最後に適用してget_fast_api_appの設定を上書き
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# デバッグ用: CORS設定を確認
logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")

# 手動でOPTIONSリクエストに対応
@app.options("/{path:path}")
async def options_handler():
    return {"message": "OK"}

if __name__ == "__main__":
    logger.info("Starting application...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=os.environ.get("PORT", 8000))
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        import traceback
        traceback.print_exc()