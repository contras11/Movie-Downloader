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

どこからでも`ytdlpcli`コマンドを実行したい場合は、pipxを使用します。

```bash
brew install pipx
pipx ensurepath
cd /path/to/Movie-Downloader
pipx install -e .
```

以降、どのディレクトリからでも`ytdlpcli`コマンドが使えます。

### 方法2: 開発環境でインストール

プロジェクトディレクトリ内で開発・使用する場合は、次の手順でインストールします。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade "pip>=26.2.2"
python -m pip install -e ".[dev]"
```

どこからでも実行できるようにするには、以下のいずれかを設定します。

<details>
<summary>オプションA: シェルエイリアスを追加</summary>

`~/.zshrc`（bashなら`~/.bashrc`）に追加します。

```bash
alias ytdlpcli='source /path/to/Movie-Downloader/.venv/bin/activate && ytdlpcli'
```

設定を反映します。
```bash
source ~/.zshrc
```
</details>

<details>
<summary>オプションB: ラッパースクリプトを作成</summary>

`~/.local/bin/ytdlpcli`を作成します。

```bash
#!/bin/bash
VENV_PATH="/path/to/Movie-Downloader/.venv"
exec "$VENV_PATH/bin/ytdlpcli" "$@"
```

実行権限を付与し、保存したディレクトリをPATHに追加します。
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

`--url-file` を明示してファイルを読み込めなかった場合は、対話入力へ切り替えず終了コード2で終了します。
URLの対話入力では空行に加えてEOF（入力の終端）でも入力を終えられます。方式やフォーマットを選択する入力がない場合は終了コード2で終了します。

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

設定JSONが破損している場合は、元ファイルを同じ場所へ `.invalid-YYYYMMDD-HHMMSS` 形式で退避し、既定設定を再生成します。一部の値だけが不正な場合は、正常な値を保持して不正値だけを既定値へ補正します。

権限不足などで設定ファイルを読み込めない場合は、元のファイルを変更せず終了します。

設定値には次の制約があります。

- `max_workers` と `format_list_limit`: 1以上の整数
- `retries`: 0以上の整数
- `format_mode`: `auto` / `mp4` / `ask` / `audio`
- `audio_format`: `mp3` / `m4a` / `opus` / `flac` / `wav`
- `download_dir` と `merge_output_format`: 空でない文字列

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
├── cli.py           # コマンドラインインターフェース
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
- 動画とプレイリストの両方を指すURLでは、`--no-playlist` により動画だけを取得します。プレイリスト自体のURLを指定すると、一覧全体が対象になる場合があります。
- askモードのフォーマット情報取得は60秒でタイムアウトし、取得できない場合は最高品質の自動選択へフォールバックします。
- 終了コードは、成功が`0`、ダウンロード失敗が`1`、入力・設定・依存エラーが`2`、ユーザーによる中断が`130`です。
- v0.1.0で進捗表示の問題を修正し、コードベースをリファクタリングしました。

## 開発とテスト

開発依存を含めてインストールし、テストを実行します。

```bash
python -m pip install --upgrade "pip>=26.2.2"
python -m pip install -e ".[dev]"
python -m pytest -q
```

GitHub ActionsではPython 3.10と3.14で同じテストを実行します。

## トラブルシュート / FAQ

**Q. 進捗表示（%、速度、ETA）が表示されない**
A. v0.1.0で修正されました。最新版に更新してください。

**Q. パーセンテージが `--.-%` と表示される**
A. 総容量が不明な場合に表示されます。進捗の計算には`total_bytes`を使い、不明な場合は`total_bytes_estimate`を使います。

**Q. フォーマット一覧が取得できない**
A. 通信や動画の制限が原因の場合があります。自動的に最高品質へフォールバックします。

**Q. `yt-dlp` が見つからないと出る**
A. `brew install yt-dlp ffmpeg` を実行してください。エラーメッセージにインストール方法が表示されます。

**Q. どのディレクトリからでも実行したい**
A. pipxでのインストール、またはシェルエイリアス/ラッパースクリプトを設定してください（インストールセクション参照）。
