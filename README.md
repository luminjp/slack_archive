# Slack Conversation Exporter Bot

このドキュメントでは、本スクリプトのインストール手順と使用方法（Bot モード／CLI モード）を説明します。

---

## 1. 前提条件

- Python 3.9 以上
- pip で以下パッケージをインストール可能な環境
  - `slack-bolt`
  - `slack-sdk`
  - `requests`


## 2. インストール

1. リポジトリをクローンまたはスクリプトをダウンロード
   ```bash
   git clone <リポジトリURL>
   cd <リポジトリディレクトリ>
   ```

2. 仮想環境の作成（推奨）
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. 必要パッケージのインストール
   ```bash
   pip install slack-bolt slack-sdk requests
   ```

4. 実行権限付与
   ```bash
   chmod +x slack_exporter.py
   ```


## 3. 設定

### 環境変数

| 変数名               | 説明                                                  | 必須   | 例                  |
| --------------------- | ----------------------------------------------------- | ------ | ------------------- |
| `SLACK_BOT_TOKEN`     | Slack Bot Token (xoxb-...)                            | Bot/CLI | xoxb-1234-…         |
| `SLACK_APP_TOKEN`     | Socket Mode 用トークン (xapp-...)                     | Bot    | xapp-1-ABCD         |
| `SLACK_SIGNING_SECRET`| Slack App の Signing Secret                           | Bot    | 012345abcdef…       |
| `TIMEZONE`            | 出力日時のタイムゾーン（IANA 名）<br>未設定時は `Asia/Tokyo` | 任意   | Europe/London       |


### OAuth スコープ

Bot モードで使用する場合、Slack アプリに以下スコープを付与し再インストールしてください。

- `commands`
- `channels:read`, `groups:read`, `im:read`, `mpim:read`
- `chat:write`
- `files:write`
- `users:read`


## 4. 使用方法

### 4.1 CLI モード

1. **会話一覧の取得**
   ```bash
   ./slack_exporter.py --list --token \$SLACK_BOT_TOKEN
   ```

2. **会話のアーカイブ**
   ```bash
   ./slack_exporter.py --archive C12345678 D87654321 --output-dir exports --token \$SLACK_BOT_TOKEN
   ```
   - `exports/` ディレクトリ配下に Markdown ファイルが出力されます。

### 4.2 Bot モード

1. 以下コマンドで実行
   ```bash
   ./slack_exporter.py --bot
   ```
   - Socket Mode を起動し、Slack のスラッシュコマンド `/export` を待機します。

2. **会話一覧**
   Slack チャンネルで以下を実行：
   ```
   /export list
   ```
   Bot が会話 ID と名前を返信します。

3. **会話アーカイブ**
   ```
   /export archive C12345678
   ```
   Bot がアーカイブを実行し、ZIP ファイルを同チャネルにアップロードします。


## 5. 出力形式

- Markdown ファイル名: `<conversation>_<yyyymmdd>.md`
- 各メッセージは日時 (`YYYY/MM/DD_HH:MM:SS`)、ユーザー名、ユーザーID、本文の順で記録
- メッセージ内のコードブロックは ``` で囲み、前後に空行を挿入


## 6. トラブルシューティング

- `not_in_channel` エラー：Bot を対象チャンネルに招待してください。<br>公開チャンネルは自動参加を試みます。
- `method_deprecated`：`files_upload_v2` を使用しますが、まだ権限が不足している場合は `files:write` を追加してください。

