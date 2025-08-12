import os
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI

APP_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(APP_DIR, "agents")
SESSION_SERVICE_URI = "sqlite:///./sessions.db"
ALLOWED_ORIGINS = [ "http://127.0.0.1", "*"]
SERVE_WEB_INTERFACE = False

load_dotenv()

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=SERVE_WEB_INTERFACE,
    # session_db_url=SESSION_SERVICE_URI,
    allow_origins=ALLOWED_ORIGINS,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=os.environ.get("PORT", 8000))