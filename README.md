# ytdlpcli

macOS向けの対話型 yt-dlp ダウンローダーです。Richで複数ジョブの進捗を表示し、フォーマット選択や並列ダウンロードに対応します。

## 特長

- 複数ジョブの進捗表示（% / 速度 / ETA / DL量）
- 音声のみダウンロード（mp3/m4a/opus/flac/wav）
- フォーマット一覧を自動取得して番号選択
- 設定ファイル `~/.ytdlpcli.json` の自動生成と更新
- 並列ダウンロード（ワーカー数は設定可）
- Ctrl+C で安全終了（実行中プロセスを停止）
- macOS のスリープ防止（caffeinate）

## インストール

### 前提条件

```bash
brew install yt-dlp ffmpeg
```

### 方法1: pipxでインストール（推奨）

どこからでも`ytdlpcli`コマンドを実行したい場合は、pipxを使用します：

```bash
brew install pipx
pipx ensurepath
cd /path/to/Movie-Downloader
pipx install -e .
```

以降、どのディレクトリからでも`ytdlpcli`コマンドが使えます。

### 方法2: 開発環境でインストール

プロジェクトディレクトリ内で開発・使用する場合：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**どこからでも実行できるようにする**には、以下のいずれかを設定：

<details>
<summary>オプションA: シェルエイリアスを追加</summary>

`~/.zshrc`（bashなら`~/.bashrc`）に追加：

```bash
alias ytdlpcli='source /path/to/Movie-Downloader/.venv/bin/activate && ytdlpcli'
```

設定を反映：
```bash
source ~/.zshrc
```
</details>

<details>
<summary>オプションB: ラッパースクリプトを作成</summary>

`~/.local/bin/ytdlpcli`を作成：

```bash
#!/bin/bash
VENV_PATH="/path/to/Movie-Downloader/.venv"
exec "$VENV_PATH/bin/ytdlpcli" "$@"
```

実行権限を付与してPATHに追加：
```bash
chmod +x ~/.local/bin/ytdlpcli
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```
</details>

## クイックスタート

```bash
ytdlpcli init-config
ytdlpcli run
```

## コマンド

### init-config

初回設定ファイルを作成します（既に存在していても正規化して保存します）。

### run

対話形式でURLを入力し、並列ダウンロードします。

#### run オプション

- `--workers` 並列数（設定を上書き）
- `--download-dir` 保存先（設定を上書き）
- `--prevent-sleep / --no-prevent-sleep` スリープ防止の切り替え
- `--mode` `auto` / `mp4` / `ask` / `audio`（フォーマット選択方式）
- `--audio-format` 音声フォーマット（audioモード時: mp3/m4a/opus/flac/wav）
- `--format-list-limit` フォーマット一覧の最大件数
- `--retries` yt-dlpのリトライ回数
- `--continue-on-error / --no-continue-on-error` 失敗時に続行するか
- `--merge-output-format` 結合後のコンテナ形式（例: mp4）
- `--url` URLを直接指定（複数可）
- `--url-file` URL一覧ファイル（1行1URL、空行と`#`は無視）

### config

設定の表示/変更を行います。

#### config オプション

- `--set-download-dir` 保存先
- `--set-workers` 並列数
- `--set-mode` `auto` / `mp4` / `ask` / `audio`
- `--set-audio-format` 音声フォーマット（mp3/m4a/opus/flac/wav）
- `--set-prevent-sleep / --set-no-prevent-sleep` スリープ防止
- `--set-format-list-limit` フォーマット一覧の最大件数
- `--set-retries` リトライ回数
- `--set-continue-on-error / --set-no-continue-on-error` 失敗時に続行するか
- `--set-merge-output-format` 結合後のコンテナ形式

## 設定ファイル

`~/.ytdlpcli.json` は初回実行時に作成されます。

```json
{
  "download_dir": "/Users/xxx/Downloads",
  "format_mode": "auto",
  "merge_output_format": "mp4",
  "max_workers": 2,
  "prevent_sleep": true,
  "format_list_limit": 12,
  "retries": 3,
  "continue_on_error": true,
  "audio_format": "mp3"
}
```

## 使い方例

```bash
# URLを対話入力
ytdlpcli run

# URLを直接指定
ytdlpcli run --url "https://www.youtube.com/watch?v=xxxx" --url "https://youtu.be/yyyy"

# URL一覧ファイルから実行
ytdlpcli run --url-file urls.txt

# mp4優先で保存（今回だけ）
ytdlpcli run --mode mp4

# 音声のみダウンロード（デフォルトmp3）
ytdlpcli run --mode audio --url "https://www.youtube.com/watch?v=xxxx"

# flac形式で音声ダウンロード
ytdlpcli run --mode audio --audio-format flac --url "https://www.youtube.com/watch?v=xxxx"

# 並列数とリトライ回数を上書き
ytdlpcli run --workers 3 --retries 5
```

## プロジェクト構造

```
src/ytdlpcli/
├── cli.py           # コマンドラインインターフェース（260行）
├── config.py        # 設定管理
├── exceptions.py    # カスタム例外クラス
├── formats.py       # フォーマット取得・解析
├── job_manager.py   # ジョブ管理と並列実行
├── runner.py        # yt-dlp実行と進捗管理
└── ui.py            # Rich UIコンポーネント
```

## 動作メモ

- `yt-dlp` と `ffmpeg` が必要です。
- 4Kなど高ビットレートでは並列数を上げると逆に遅くなることがあります（推奨は2〜3）。
- プレイリストは `--no-playlist` で無効化しています。
- v0.1.0で進捗表示の問題を修正し、コードベースを大幅にリファクタリングしました。

## トラブルシュート / FAQ

**Q. 進捗表示（%、速度、ETA）が表示されない**
A. v0.1.0で修正されました。最新版に更新してください。

**Q. パーセンテージが `--.-%` と表示される**
A. v0.1.0で修正されました。`total_bytes`と`total_bytes_estimate`の両方をチェックするようになりました。

**Q. フォーマット一覧が取得できない**
A. 通信や動画の制限が原因の場合があります。自動的に最高品質へフォールバックします。

**Q. `yt-dlp` が見つからないと出る**
A. `brew install yt-dlp ffmpeg` を実行してください。親切なエラーメッセージでインストール方法が表示されます。

**Q. どのディレクトリからでも実行したい**
A. pipxでのインストール、またはシェルエイリアス/ラッパースクリプトを設定してください（インストールセクション参照）。
