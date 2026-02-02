# ytdlpcli

macOS向けの対話型 yt-dlp ダウンローダーです。Richで複数ジョブの進捗を表示し、フォーマット選択や並列ダウンロードに対応します。

## 特長

- 複数ジョブの進捗表示（% / 速度 / ETA / DL量）
- フォーマット一覧を自動取得して番号選択
- 設定ファイル `~/.ytdlpcli.json` の自動生成と更新
- 並列ダウンロード（ワーカー数は設定可）
- Ctrl+C で安全終了（実行中プロセスを停止）
- macOS のスリープ防止（caffeinate）

## インストール

```bash
brew install yt-dlp ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

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
- `--mode` `auto` / `mp4` / `ask`（フォーマット選択方式）
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
- `--set-mode` `auto` / `mp4` / `ask`
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
  "continue_on_error": true
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

# 並列数とリトライ回数を上書き
ytdlpcli run --workers 3 --retries 5
```

## 動作メモ

- `yt-dlp` と `ffmpeg` が必要です。
- 4Kなど高ビットレートでは並列数を上げると逆に遅くなることがあります（推奨は2〜3）。
- プレイリストは `--no-playlist` で無効化しています。

## トラブルシュート / FAQ

**Q. 速度やETAが `--` になることがある**  
A. 総容量が不明な場合は `yt-dlp` 側が推定できないため表示されません。

**Q. フォーマット一覧が取得できない**  
A. 通信や動画の制限が原因の場合があります。自動的に最高品質へフォールバックします。

**Q. `yt-dlp` が見つからないと出る**  
A. `brew install yt-dlp ffmpeg` を実行してください。
