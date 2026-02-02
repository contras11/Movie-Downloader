# ytdlpcli

macOS向けの対話型 yt-dlp ダウンローダーです。Richで複数ジョブの進捗を表示し、フォーマット選択や並列ダウンロードに対応します。

## セットアップ

```bash
brew install yt-dlp ffmpeg
pip install -e .
```

## 使い方

```bash
ytdlpcli init-config
ytdlpcli run
```

設定ファイルは `~/.ytdlpcli.json` に作成されます。
