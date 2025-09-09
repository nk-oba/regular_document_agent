# Artifact 保存ユーザー ID 管理ヘルパー

このモジュールは、ADK (Application Development Kit) での Artifact 保存時に適切なユーザー ID 管理を提供します。

## 主な機能

### 1. 統一されたユーザー ID 生成

- **安定したユーザー ID**: email アドレスから 16 文字の SHA256 ハッシュを生成
- **正規化処理**: 大文字小文字の統一、空白の除去
- **一貫性保証**: 同じ email から常に同じユーザー ID を生成

### 2. セッション管理システムとの統合

- **複数のソース対応**: ファイルベース、データベースベースのセッション情報
- **フォールバック機能**: 認証情報が取得できない場合の anonymous 処理
- **エラーハンドリング**: 堅牢なエラー処理と詳細なログ出力

### 3. 適切な Artifact 保存

- **自動ユーザー ID 管理**: セッション情報から自動的にユーザー ID を特定
- **詳細な保存結果**: 成功/失敗、バージョン、ダウンロード URL 等の情報
- **エラー処理**: 保存失敗時の適切なエラー情報

## 使用方法

### 基本的な使用例

```python
from utils.artifact_user_helper import save_artifact_with_proper_user_id, format_download_section

# Artifactオブジェクトの作成
csv_artifact = types.Part.from_bytes(
    data=csv_bytes,
    mime_type="text/csv"
)

# 適切なユーザー管理でArtifactを保存
save_result = await save_artifact_with_proper_user_id(
    tool_context=tool_context,
    filename="report.csv",
    artifact=csv_artifact,
    return_detailed_info=True
)

# フォーマット済みダウンロードセクション生成
if save_result['success']:
    download_section = format_download_section(save_result)
    print(f"📥 ダウンロード情報:\n{download_section}")
else:
    print(f"❌ 保存エラー: {save_result.get('error')}")
```

### ユーザー ID 生成のみ

```python
from utils.artifact_user_helper import get_adk_stable_user_id_from_email

# emailからADK用の安定したユーザーIDを生成
user_id = get_adk_stable_user_id_from_email("user@example.com")
print(f"ADK User ID: {user_id}")  # 出力例: b4c9a289323b21a0
```

## アーキテクチャ

### ユーザー ID 取得の優先順位

1. **SQLite データベース**: `sessions.db`から最新のアクティブユーザー情報
2. **ファイルベースセッション**: `auth_storage/sessions/auth_sessions/`の有効なセッション
3. **フォールバック**: `anonymous`ユーザーとして処理

### セッション情報の取得

```python
# InvocationContextからセッション情報を取得
invocation_ctx = tool_context.invocation_context
session_id = invocation_ctx.invocation_id

# 対応するユーザー情報をデータベースから検索
# email形式の場合は自動的にADK User IDに変換
```

### ダウンロード URL 生成

生成される URL:

- **プライマリ**: `/download/artifact/{app_name}/{user_id}/{session_id}/{filename}`
- **API 形式**: `/apps/{app_name}/users/{user_id}/{session_id}/artifacts/{filename}`
- **Invocation 基準**: `/download/artifact/by-invocation/{session_id}/{filename}`

## 返り値の構造

### save_result の例

```python
{
    'success': True,
    'filename': 'report.csv',
    'version': 1,
    'user_id': 'b4c9a289323b21a0',
    'session_id': 'inv-12345-67890',
    'is_authenticated': True,
    'email': 'user@example.com',
    'source': 'database_email_converted',
    'download_urls': {
        'primary': 'http://localhost:8000/download/artifact/...',
        'api': 'http://localhost:8000/apps/...',
        'invocation': 'http://localhost:8000/download/artifact/by-invocation/...'
    },
    'app_name': 'document_creating_agent'
}
```

## テスト

```bash
cd agents
python3 test_artifact_helper.py
```

### テスト内容

- ✅ ヘルパー関数のインポート
- ✅ ユーザー ID 生成（16 文字、一貫性）
- ✅ セッション情報取得
- ✅ Artifact 保存（モック）
- ✅ ダウンロードセクション生成

## ログ出力

```
INFO:utils.artifact_user_helper:Found invocation_id: inv-12345-67890
INFO:utils.artifact_user_helper:Found recent user_id from database: user@example.com
INFO:utils.artifact_user_helper:Converted email to ADK user ID: user@... -> b4c9a289323b21a0
INFO:utils.artifact_user_helper:Artifact saved successfully: report.csv (version 1)
```

## 移行

### 従来のコードから

```python
# 旧実装
version = await tool_context.save_artifact(filename=filename, artifact=artifact)
download_url = f"http://localhost:8000/download/artifact/{app_name}/{user_id}/{session_id}/{filename}"

# 新実装
save_result = await save_artifact_with_proper_user_id(
    tool_context=tool_context, filename=filename, artifact=artifact
)
download_section = format_download_section(save_result)
```

### メリット

- 🔒 **セキュリティ**: 適切なユーザー識別とアクセス制御
- 🔄 **一貫性**: 全ての保存処理で統一されたロジック
- 🛠️ **保守性**: 中央集約された管理でメンテナンスが容易
- 📊 **可視性**: 詳細なログとエラー情報
- ⚡ **パフォーマンス**: 効率的なデータベースアクセス

## 依存関係

- `sqlite3`: セッションデータベースアクセス
- `hashlib`: ユーザー ID 生成
- `pathlib`: ファイルパス操作
- `json`: セッション情報の処理
- `logging`: ログ出力
