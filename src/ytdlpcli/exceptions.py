"""
ytdlpcli.exceptions
~~~~~~~~~~~~~~~~~~~

ytdlpcli固有の例外クラスを定義します。
"""


class YtdlpCliError(Exception):
    """ytdlpcliの基底例外クラス"""
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


class ConfigError(YtdlpCliError):
    """設定ファイルの読み書きに失敗した場合の例外"""
    pass


class UrlFileReadError(YtdlpCliError):
    """URL一覧ファイルの読み込みに失敗した場合の例外"""
    pass


class DownloadError(YtdlpCliError):
    """ダウンロード処理に失敗した場合の例外"""
    pass
