"""ロギングユーティリティ (§17 準拠)"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_JST = timezone(timedelta(hours=9))


def setup_logging(
    *,
    verbose: bool = False,
    log_dir: Path | None = None,
    tz_name: str = "Asia/Tokyo",
) -> None:
    """stdout + ファイル のデュアルロギングを初期化する。

    Args:
        verbose: True なら DEBUG、False なら INFO
        log_dir: ログファイル出力ディレクトリ（None なら logs/）
        tz_name: タイムゾーン名（ファイル名用）
    """
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 既存ハンドラを除去（重複防止）
    root_logger.handlers.clear()

    # stdout ハンドラ
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root_logger.addHandler(stdout_handler)

    # ファイルハンドラ
    if log_dir is None:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now(_JST).strftime("%Y-%m-%d")
    log_file = log_dir / f"{today_str}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root_logger.addHandler(file_handler)

    # httpx のログを抑制
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
