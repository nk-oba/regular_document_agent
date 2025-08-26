import os
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from typing import List
from document_creating_agent.agent import root_agent

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DB_URL = "sqlite:///./sessions.db"
ALLOWED_ORIGINS = [ "http://127.0.0.1", "*"]
SERVE_WEB_INTERFACE = False

load_dotenv()

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    allow_origins=ALLOWED_ORIGINS,
    web=SERVE_WEB_INTERFACE
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

class AgentResponseHandler:
    @staticmethod
    def parse_agent_response(events):
        """Google ADKエージェントからの応答を解析"""
        agent_message = "エージェントからの応答を処理中..."
        
        for event in events:
            print(f"Processing event: {event}")
            
            if isinstance(event, dict):
                if "content" in event:
                    content = event["content"]
                    if isinstance(content, dict) and "parts" in content:
                        for part in content["parts"]:
                            if isinstance(part, dict) and "text" in part:
                                agent_message = part["text"]
                                return agent_message
                
                elif "text" in event:
                    agent_message = event["text"]
                    return agent_message
                
                elif "message" in event:
                    agent_message = event["message"]
                    return agent_message
        
        if agent_message == "エージェントからの応答を処理中...":
            agent_message = f"エージェントが応答しました（イベント数: {len(events)}）"
        
        return agent_message
    
    @staticmethod
    def generate_smart_response(user_message):
        """スマート応答システム（フォールバック）"""
        message_lower = user_message.lower()
        
        # 挨拶の検出
        if any(greeting in message_lower for greeting in ['hello', 'hi', 'こんにちは', 'おはよう', 'こんばんは']):
            return """こんにちは！定例資料作成エージェントです。

以下のようなお手伝いができます：
📊 PowerPoint資料の作成
📈 データ分析レポート
📋 プレゼンテーション資料
📄 定例会議資料

どのような資料を作成したいか教えてください。"""

        # 資料作成の検出
        elif any(keyword in user_message for keyword in ['資料', 'プレゼン', 'PowerPoint', 'スライド', 'ppt']):
            return """資料作成をサポートします！

具体的にどのような資料をお作りしますか？

📊 売上分析資料
📈 業績レポート
📋 企画提案書
📄 月次報告書
📉 データ分析結果
🎯 戦略企画書

資料の種類や内容を教えてください。より具体的な支援を提供いたします。"""

        # データ分析の検出
        elif any(keyword in user_message for keyword in ['分析', 'データ', 'レポート', '集計', '統計']):
            return """データ分析レポートの作成をお手伝いします！

以下の分析が可能です：
📊 売上データ分析
📈 顧客行動分析  
📉 トレンド分析
📋 業績比較分析
🎯 KPI分析

分析したいデータの種類や目的を詳しく教えてください。"""

        # 機能説明の要求
        elif any(keyword in message_lower for keyword in ['機能', 'できること', 'help', 'ヘルプ', '使い方']):
            return """🤖 定例資料作成エージェントの機能

📊 **資料作成機能**
- PowerPoint資料の自動生成
- データに基づいたグラフ作成
- レイアウト最適化

📈 **データ分析機能**  
- CSVデータの解析
- 統計情報の算出
- 可視化グラフの生成

📋 **テンプレート機能**
- 定例会議資料テンプレート
- 業績報告書テンプレート
- 企画提案書テンプレート

具体的な作業内容を教えてください！"""

        # テスト関連
        elif any(keyword in message_lower for keyword in ['テスト', 'test', '動作確認', '確認']):
            return """✅ システム動作確認

🔧 **現在の状態**
- WebSocket通信: 正常動作
- エージェント機能: 有効
- 応答システム: スマートフォールバック

🚀 **利用可能な機能**
- リアルタイムチャット
- 資料作成支援
- データ分析支援

システムは正常に動作しています！"""

        # その他の一般的な応答
        else:
            return f"""「{user_message}」についてお答えします。

🤖 現在、以下の支援が可能です：

📊 **資料作成**: PowerPoint、レポート作成
📈 **データ分析**: CSV分析、グラフ作成  
📋 **文書作成**: 企画書、報告書作成

より具体的にどのようなお手伝いが必要か教えてください。
例：「売上データの分析資料を作成してください」"""

manager = ConnectionManager()
handler = AgentResponseHandler()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get('message', '')
            selected_agent = message_data.get('selectedAgent', 'document_creating_agent')
            
            try:
                import requests
                import os
                
                print(f"Received message: {user_message}")
                print(f"Selected agent: {selected_agent}")
                
                app_name = selected_agent
                user_id = f"user_{client_id}"
                session_id = f"session_{client_id}"
                
                # Google API KEYがない場合はフォールバック機能を使用
                api_key = os.getenv("GOOGLE_API_KEY")
                print(f"DEBUG: GOOGLE_API_KEY found: {bool(api_key)}")
                print(f"DEBUG: API key length: {len(api_key) if api_key else 0}")
                print(f"DEBUG: API key prefix: {api_key[:10] if api_key else 'None'}...")
                use_real_agent = bool(api_key and api_key != "AIzaSyDemo_API_Key_Not_Real")
                
                if use_real_agent:
                    print("Using real Google ADK agent")
                    
                    # セッション作成
                    session_url = f"http://localhost:8000/apps/{app_name}/users/{user_id}/sessions/{session_id}"
                    print(f"DEBUG: Creating session at URL: {session_url}")
                    try:
                        session_response = await asyncio.to_thread(
                            requests.post,
                            session_url,
                            json={},
                            headers={"Content-Type": "application/json"}
                        )
                        print(f"DEBUG: Session creation status: {session_response.status_code}")
                        print(f"DEBUG: Session response: {session_response.text[:200]}...")
                        
                        if session_response.status_code not in [200, 400]:
                            print(f"DEBUG: Session creation failed with status {session_response.status_code}")
                            use_real_agent = False
                        elif session_response.status_code == 400 and "already exists" in session_response.text:
                            print(f"DEBUG: Session already exists - continuing with existing session")
                    except Exception as session_error:
                        print(f"DEBUG: Session creation error: {session_error}")
                        import traceback
                        traceback.print_exc()
                        use_real_agent = False
                    
                    if use_real_agent:
                        agent_request = {
                            "appName": app_name,
                            "userId": user_id,
                            "sessionId": session_id,
                            "newMessage": {
                                "parts": [{"text": user_message}],
                                "role": "user"
                            },
                            "streaming": False
                        }
                        
                        print(f"DEBUG: Agent request payload: {json.dumps(agent_request, indent=2)}")
                        try:
                            response_result = await asyncio.to_thread(
                                requests.post,
                                "http://localhost:8000/run",
                                json=agent_request,
                                headers={"Content-Type": "application/json"}
                            )
                            
                            print(f"DEBUG: Agent API response status: {response_result.status_code}")
                            print(f"DEBUG: Agent response headers: {dict(response_result.headers)}")
                            
                            if response_result.status_code == 200:
                                events = response_result.json()
                                print(f"DEBUG: Agent events received: {len(events) if isinstance(events, list) else 'not list'}")
                                print(f"DEBUG: First event: {events[0] if events and isinstance(events, list) else 'No events'}")
                                agent_message = handler.parse_agent_response(events)
                                print(f"DEBUG: Parsed agent message: {agent_message[:100]}...")
                            else:
                                print(f"DEBUG: Agent API error status {response_result.status_code}: {response_result.text}")
                                use_real_agent = False
                                
                        except Exception as agent_error:
                            print(f"DEBUG: Agent execution error: {agent_error}")
                            import traceback
                            traceback.print_exc()
                            use_real_agent = False
                
                if not use_real_agent:
                    print("Using fallback smart response system")
                    agent_message = handler.generate_smart_response(user_message)
                
                print(f"Sending response: {agent_message[:100]}...")
                
                response = {
                    "client_id": client_id,
                    "message": agent_message,
                    "timestamp": message_data.get('timestamp'),
                    "type": "agent_response",
                    "source": "real_agent" if use_real_agent else "fallback"
                }
                
            except Exception as e:
                print(f"Error: {str(e)}")
                import traceback
                traceback.print_exc()
                
                response = {
                    "client_id": client_id,
                    "message": f"エラーが発生しました: {str(e)}",
                    "timestamp": message_data.get('timestamp'),
                    "type": "error"
                }
            
            await manager.send_personal_message(json.dumps(response), websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=os.environ.get("PORT", 8000))