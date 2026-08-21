"""cli.py の入力・終了コードテスト"""

import argparse
from unittest.mock import Mock, patch

import pytest

from ytdlpcli.cli import _read_urls_from_args, build_parser, main
from ytdlpcli.exceptions import UrlFileReadError, YtdlpCliError


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--workers", "0"],
        ["run", "--format-list-limit", "0"],
        ["run", "--retries", "-1"],
        ["run", "--merge-output-format", "   "],
        ["config", "--set-mode", "invalid"],
        ["config", "--set-audio-format", "invalid"],
    ],
)
def test_invalid_cli_values_exit_with_code_2(arguments):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(arguments)

    assert exc_info.value.code == 2


def test_missing_url_file_does_not_fall_back_to_interactive_input(tmp_path):
    args = argparse.Namespace(url=None, url_file=str(tmp_path / "missing.txt"))

    with pytest.raises(UrlFileReadError):
        _read_urls_from_args(args)


def test_invalid_utf8_url_file_is_reported_as_input_error(tmp_path):
    url_file = tmp_path / "urls.txt"
    url_file.write_bytes(b"\xff\xfe")
    args = argparse.Namespace(url=None, url_file=str(url_file))

    with pytest.raises(UrlFileReadError):
        _read_urls_from_args(args)


def test_main_converts_keyboard_interrupt_to_exit_code_130():
    parser = Mock()
    parser.parse_args.return_value = argparse.Namespace(func=Mock(side_effect=KeyboardInterrupt))

    with patch("ytdlpcli.cli.build_parser", return_value=parser):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 130


def test_main_converts_expected_cli_error_to_exit_code_2():
    parser = Mock()
    parser.parse_args.return_value = argparse.Namespace(func=Mock(side_effect=YtdlpCliError("input error")))

    with patch("ytdlpcli.cli.build_parser", return_value=parser):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 2
