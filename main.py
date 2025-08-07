from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
import os
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# ADKエージェントを使用するかどうかのフラグ
USE_ADK_AGENT = os.getenv("USE_ADK_AGENT", "false").lower() == "true"

if USE_ADK_AGENT:
    try:
        # ADKエージェントのインポートを試行
        from document_creating_agent.agent import root_agent
        logging.info("ADK Agent loaded successfully")
        ADK_AGENT_AVAILABLE = True
    except Exception as e:
        logging.warning(f"Failed to load ADK Agent: {e}")
        ADK_AGENT_AVAILABLE = False
else:
    ADK_AGENT_AVAILABLE = False

# フォールバック：Google Generative AI
if not ADK_AGENT_AVAILABLE:
    try:
        import google.generativeai as genai
        from google.cloud import aiplatform
        
        # Vertex AIの初期化
        project_id = os.getenv("PROJECT_ID")
        location = os.getenv("LOCATION", "us-central1")
        
        if project_id:
            aiplatform.init(project=project_id, location=location)
        
        GENAI_AVAILABLE = True
    except Exception as e:
        logging.warning(f"Failed to load Google Generative AI: {e}")
        GENAI_AVAILABLE = False

def get_ai_response(message: str) -> str:
    if ADK_AGENT_AVAILABLE:
        try:
            # ADKエージェントを使用
            response = root_agent.send_prompt(message)
            return response
        except Exception as e:
            logging.error(f"ADK Agent error: {e}")
            return f"ADKエージェントエラー: {str(e)}"
    
    elif GENAI_AVAILABLE:
        try:
            # Google Generative AI (Gemini) を使用
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(message)
                return response.text
            else:
                return f"テストレスポンス: {message} を受信しました。API_KEYが設定されていません。"
        except Exception as e:
            logging.error(f"Generative AI error: {e}")
            return f"Generative AIエラー: {str(e)}"
    
    else:
        # 最終的なフォールバック
        return f"テストレスポンス: {message} を受信しました。AIサービスが利用できません。"

app = FastAPI(title="Document Creating Agent API")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.jsのデフォルトポート
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MessageRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

class MessageResponse(BaseModel):
    response: str
    conversation_id: str

@app.post("/chat", response_model=MessageResponse)
async def chat(request: MessageRequest):
    try:
        # 会話IDの生成
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # AI接続でレスポンス生成
        response = get_ai_response(request.message)
        
        return MessageResponse(
            response=response,
            conversation_id=conversation_id
        )
    except Exception as e:
        logging.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)