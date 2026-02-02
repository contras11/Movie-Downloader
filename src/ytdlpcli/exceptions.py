"""
ytdlpcli.exceptions
~~~~~~~~~~~~~~~~~~~

ytdlpcli固有の例外クラスを定義します。
"""


class YtdlpCliError(Exception):
    """ytdlpclの基底例外クラス"""
    pass


class YtdlpNotFoundError(YtdlpCliError):
    """yt-dlp実行ファイルが見つからない場合の例外"""

    def __init__(self):
        super().__init__(
            "yt-dlpが見つかりません。以下のコマンドでインストールしてください:\n"
            "  brew install yt-dlp ffmpeg"
        )


class FormatFetchError(YtdlpCliError):
    """フォーマット情報の取得に失敗した場合の例外"""
    pass


class DownloadError(YtdlpCliError):
    """ダウンロード処理に失敗した場合の例外"""
    pass
