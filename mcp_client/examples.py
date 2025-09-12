"""
使用例とサンプルコード
MCP認証フレームワークの実際の使用例
"""

import asyncio
import os
from typing import Optional
from agents.mcp_client import MCPAuthClient
from agents.mcp_client.transport.http_client import SimpleAuthenticatedClient, AuthenticatedHTTPClient
from agents.mcp_client.integration import MCPClientFactory
from agents.mcp_client.config.settings import MCPClientConfig, ServerConfig
from agents.mcp_client.error_handler import with_error_handling


# ==============================================================================
# 基本的な使用例
# ==============================================================================

async def basic_authentication_example():
    """基本的な認証と API 呼び出しの例"""
    server_url = "https://mcp-server.example.com"
    
    async with MCPAuthClient(server_url, user_id="user123") as client:
        try:
            # 自動認証付きでAPIを呼び出し
            response = await client.make_authenticated_request("GET", "/api/user/profile")
            
            if response.status_code == 200:
                user_data = response.json()
                print(f"User profile: {user_data}")
            else:
                print(f"API call failed: {response.status_code}")
                
        except Exception as e:
            print(f"Authentication failed: {e}")


async def interactive_authentication_example():
    """対話的認証の例"""
    
    def handle_authentication(auth_url: str):
        """認証URLが提供された時の処理"""
        print(f"\n🔐 Authentication Required")
        print(f"Please visit the following URL to authenticate:")
        print(f"{auth_url}")
        print("After authentication, press Enter to continue...")
        input()
    
    server_url = "https://mcp-server.example.com"
    
    async with SimpleAuthenticatedClient(
        server_url, 
        user_id="interactive_user",
        auth_callback=handle_authentication
    ) as client:
        
        print("Making API request...")
        response = await client.get("/api/resources")
        
        if response.status_code == 200:
            resources = response.json()
            print(f"Retrieved {len(resources.get('items', []))} resources")
        else:
            print(f"Failed to retrieve resources: {response.status_code}")


# ==============================================================================
# 設定例
# ==============================================================================

def advanced_configuration_example():
    """高度な設定の例"""
    
    # グローバル設定
    config = MCPClientConfig(
        timeout=120,                    # 2分のタイムアウト
        max_retries=5,                  # 最大5回リトライ
        token_cache_ttl=900,            # 15分のキャッシュ
        require_https=True,             # HTTPS必須
        validate_ssl=True,              # SSL検証有効
        default_redirect_uri='http://localhost:8080/auth/callback'
    )
    
    # サーバー固有設定
    server_configs = [
        ServerConfig(
            url="https://api.example.com",
            name="Main API Server",
            scopes=['read', 'write', 'admin'],
            redirect_uri='http://localhost:8080/callback/main'
        ),
        ServerConfig(
            url="https://analytics.example.com", 
            name="Analytics Server",
            scopes=['analytics:read', 'reports:generate'],
            redirect_uri='http://localhost:8080/callback/analytics'
        )
    ]
    
    # 設定に追加
    for server_config in server_configs:
        config.add_server(server_config)
    
    return config


async def multi_server_example():
    """複数サーバー対応の例"""
    config = advanced_configuration_example()
    
    servers = [
        "https://api.example.com",
        "https://analytics.example.com"
    ]
    
    # 各サーバーに対してクライアント作成
    clients = {}
    for server_url in servers:
        clients[server_url] = MCPAuthClient(server_url, "multi_user", config)
    
    try:
        # 全てのクライアントで並行してデータ取得
        tasks = []
        for server_url, client in clients.items():
            async def fetch_data(server, client):
                async with client:
                    response = await client.make_authenticated_request("GET", "/api/status")
                    return server, response.json() if response.status_code == 200 else None
            
            tasks.append(fetch_data(server_url, client))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Error: {result}")
            else:
                server, data = result
                print(f"Server {server}: {data}")
                
    finally:
        # クライアントのクリーンアップ
        for client in clients.values():
            await client.close()


# ==============================================================================
# エラーハンドリング例
# ==============================================================================

@with_error_handling()
async def error_handling_example():
    """エラーハンドリング付きAPI呼び出しの例"""
    
    async with MCPAuthClient("https://unreliable-server.example.com") as client:
        
        # 複数のAPIエンドポイントを試行
        endpoints = ["/api/v1/data", "/api/v2/data", "/api/legacy/data"]
        
        for endpoint in endpoints:
            try:
                response = await client.make_authenticated_request("GET", endpoint)
                if response.status_code == 200:
                    print(f"Success with {endpoint}: {response.json()}")
                    return response.json()
                else:
                    print(f"Failed {endpoint}: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"Exception with {endpoint}: {e}")
                continue
        
        raise Exception("All endpoints failed")


async def retry_with_backoff_example():
    """リトライとバックオフの例"""
    from agents.mcp_client.error_handler import with_circuit_breaker
    
    @with_circuit_breaker(failure_threshold=3, reset_timeout=60)
    async def api_call_with_circuit_breaker():
        async with MCPAuthClient("https://flaky-server.example.com") as client:
            return await client.make_authenticated_request("GET", "/api/data")
    
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            response = await api_call_with_circuit_breaker()
            print(f"Success on attempt {attempt + 1}")
            return response
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_attempts - 1:
                wait_time = (2 ** attempt) * 1.0  # Exponential backoff
                print(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
    
    print("All attempts exhausted")


# ==============================================================================
# Web フレームワーク統合例
# ==============================================================================

def fastapi_integration_example():
    """FastAPI統合の例"""
    try:
        from fastapi import FastAPI, Depends, HTTPException
        from agents.mcp_client.integration import WebIntegration
        
        app = FastAPI(title="MCP Authenticated API")
        
        # 認証依存関数を作成
        auth_dependency = WebIntegration.create_fastapi_auth_dependency(
            "https://mcp-server.example.com"
        )
        
        @app.get("/profile")
        async def get_user_profile(token: str = Depends(auth_dependency)):
            """認証が必要なユーザープロファイル取得"""
            
            async with MCPAuthClient("https://mcp-server.example.com") as client:
                # トークンを使って外部APIを呼び出し
                response = await client.make_authenticated_request(
                    "GET", "/api/user/profile"
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to fetch profile"
                    )
        
        @app.get("/public")
        async def public_endpoint():
            """認証不要のパブリックエンドポイント"""
            return {"message": "This is a public endpoint"}
        
        return app
        
    except ImportError:
        print("FastAPI not installed. Install with: pip install fastapi")
        return None


def flask_integration_example():
    """Flask統合の例"""
    try:
        from flask import Flask, jsonify, request
        from agents.mcp_client.integration import WebIntegration
        
        app = Flask(__name__)
        
        # 認証デコレータを作成
        require_auth = WebIntegration.create_flask_auth_decorator(
            "https://mcp-server.example.com"
        )
        
        @app.route("/profile")
        @require_auth
        def get_user_profile():
            """認証が必要なユーザープロファイル取得"""
            
            # 実際の実装では async/await を適切に処理する必要があります
            # ここは簡略化した例です
            return jsonify({
                "user_id": "123",
                "name": "John Doe",
                "email": "john@example.com"
            })
        
        @app.route("/public")
        def public_endpoint():
            """認証不要のパブリックエンドポイント"""
            return jsonify({"message": "This is a public endpoint"})
        
        return app
        
    except ImportError:
        print("Flask not installed. Install with: pip install flask")
        return None


# ==============================================================================
# CLI 統合例
# ==============================================================================

def cli_integration_example():
    """CLI統合の例"""
    try:
        import click
        from agents.mcp_client.integration import CLIIntegration
        
        @click.group()
        def cli():
            """MCP Client CLI Example"""
            pass
        
        # 認証コマンドを追加
        auth_command = CLIIntegration.create_click_auth_command(
            "https://mcp-server.example.com"
        )
        cli.add_command(auth_command, name="auth")
        
        @cli.command()
        @click.option('--user-id', help='User ID')
        @click.option('--format', type=click.Choice(['json', 'table']), default='json')
        def list_resources(user_id: Optional[str], format: str):
            """List available resources"""
            
            async def fetch_resources():
                async with MCPAuthClient(
                    "https://mcp-server.example.com", 
                    user_id=user_id
                ) as client:
                    response = await client.make_authenticated_request("GET", "/api/resources")
                    
                    if response.status_code == 200:
                        resources = response.json()
                        
                        if format == 'json':
                            click.echo(response.text)
                        else:
                            # テーブル形式での出力
                            for resource in resources.get('items', []):
                                click.echo(f"ID: {resource.get('id')}, Name: {resource.get('name')}")
                    else:
                        click.echo(f"Failed to fetch resources: {response.status_code}", err=True)
            
            asyncio.run(fetch_resources())
        
        @cli.command()
        @click.option('--server', help='Server URL')
        def status(server: Optional[str]):
            """Check authentication status"""
            server_url = server or "https://mcp-server.example.com"
            
            async def check_status():
                async with MCPAuthClient(server_url) as client:
                    is_auth = await client.is_authenticated()
                    
                    if is_auth:
                        click.echo("✅ Authenticated")
                        
                        # トークン情報を表示
                        token_info = client.token_manager.get_token_info()
                        if token_info:
                            expires_in = client.token_manager.get_expires_in()
                            if expires_in:
                                click.echo(f"Token expires in: {expires_in} seconds")
                    else:
                        click.echo("❌ Not authenticated")
            
            asyncio.run(check_status())
        
        return cli
        
    except ImportError:
        print("Click not installed. Install with: pip install click")
        return None


# ==============================================================================
# バッチ処理例
# ==============================================================================

async def batch_processing_example():
    """バッチ処理の例"""
    
    async def process_batch(client: MCPAuthClient, items: list, batch_size: int = 10):
        """アイテムをバッチ処理"""
        results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            batch_results = []
            
            # バッチ内のアイテムを並行処理
            tasks = []
            for item in batch:
                task = client.make_authenticated_request(
                    "POST", "/api/process",
                    json={"item_id": item["id"], "data": item["data"]}
                )
                tasks.append(task)
            
            batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, response in enumerate(batch_responses):
                if isinstance(response, Exception):
                    print(f"Failed to process item {batch[j]['id']}: {response}")
                    batch_results.append({"id": batch[j]["id"], "status": "failed", "error": str(response)})
                elif response.status_code == 200:
                    batch_results.append({"id": batch[j]["id"], "status": "success", "result": response.json()})
                else:
                    batch_results.append({"id": batch[j]["id"], "status": "failed", "http_code": response.status_code})
            
            results.extend(batch_results)
            
            # バッチ間の待機時間（レート制限対策）
            if i + batch_size < len(items):
                await asyncio.sleep(1.0)
        
        return results
    
    # サンプルデータ
    items_to_process = [
        {"id": f"item_{i}", "data": f"data_{i}"}
        for i in range(50)
    ]
    
    async with MCPAuthClient("https://batch-processor.example.com") as client:
        results = await process_batch(client, items_to_process, batch_size=5)
        
        # 結果の集計
        success_count = len([r for r in results if r["status"] == "success"])
        failed_count = len([r for r in results if r["status"] == "failed"])
        
        print(f"Batch processing completed:")
        print(f"✅ Success: {success_count}")
        print(f"❌ Failed: {failed_count}")


# ==============================================================================
# モニタリングとログ例
# ==============================================================================

def monitoring_example():
    """モニタリングとログの例"""
    import logging
    from agents.mcp_client.error_handler import ErrorHandler
    
    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('mcp_client.log'),
            logging.StreamHandler()
        ]
    )
    
    # カスタムエラーハンドラー
    error_handler = ErrorHandler(log_errors=True)
    
    async def monitored_api_call():
        """モニタリング付きAPI呼び出し"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with MCPAuthClient("https://monitored-server.example.com") as client:
                response = await client.make_authenticated_request("GET", "/api/metrics")
                
                end_time = asyncio.get_event_loop().time()
                duration = end_time - start_time
                
                logging.info(f"API call completed in {duration:.2f} seconds")
                logging.info(f"Response status: {response.status_code}")
                
                return response
                
        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            
            logging.error(f"API call failed after {duration:.2f} seconds: {e}")
            error_handler.handle_error(e, {"duration": duration})
            raise
    
    return monitored_api_call


# ==============================================================================
# メイン実行例
# ==============================================================================

async def main():
    """メイン実行関数"""
    print("🚀 MCP Client Examples")
    print("=" * 50)
    
    # 基本例の実行
    print("\n1. Basic Authentication Example")
    try:
        await basic_authentication_example()
    except Exception as e:
        print(f"Example failed: {e}")
    
    # 設定例の表示
    print("\n2. Advanced Configuration Example")
    config = advanced_configuration_example()
    print(f"Created config with {len(config.list_servers())} servers")
    
    # エラーハンドリング例
    print("\n3. Error Handling Example")
    try:
        await error_handling_example()
    except Exception as e:
        print(f"Error handling example completed: {e}")
    
    # モニタリング例
    print("\n4. Monitoring Example")
    monitored_call = monitoring_example()
    try:
        await monitored_call()
    except Exception as e:
        print(f"Monitoring example completed: {e}")
    
    print("\n✅ Examples completed!")


if __name__ == "__main__":
    # 環境設定のサンプル
    os.environ.setdefault('MCP_CLIENT_LOG_LEVEL', 'INFO')
    os.environ.setdefault('MCP_CLIENT_TIMEOUT', '30')
    
    # サンプルの実行
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Examples interrupted by user")
    except Exception as e:
        print(f"❌ Examples failed: {e}")
        import traceback
        traceback.print_exc()