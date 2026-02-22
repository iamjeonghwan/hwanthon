"""Simple FTP file downloader.

This script prompts for FTP connection details (server IP/hostname, user ID,
and password) and downloads a specified file. Use it from a terminal to fetch
files from an FTP server without hard-coding credentials.
"""

from __future__ import annotations

# =============================================================================
# 🔴 하드코딩 영역 (아래 값을 실제 환경에 맞게 수정하세요)
# =============================================================================
FTP_HOST: str | None = None  # 🔴 하드코딩: FTP 서버 IP 또는 호스트명 (예: "192.168.1.100")
FTP_USER: str | None = None  # 🔴 하드코딩: FTP 사용자 ID
FTP_PASSWORD: str | None = None  # 🔴 하드코딩: FTP 비밀번호
FTP_PORT: int = 21  # 🔴 하드코딩: FTP 포트 (기본 21)
# =============================================================================

import argparse
import ftplib
import getpass
from pathlib import Path
from typing import Callable


def prompt_if_missing(value: str | None, prompt_text: str, secret: bool = False) -> str:
    """Return the provided value or prompt the user if it is missing."""

    if value:
        return value

    # Use a hidden prompt for secrets like passwords.
    prompt: Callable[[str], str] = getpass.getpass if secret else input
    return prompt(prompt_text).strip()


def download_file(
    host: str,
    username: str,
    password: str,
    remote_path: str,
    local_path: Path,
    *,
    port: int = 21,
    passive: bool = True,
) -> None:
    """Download a single file from an FTP server."""

    with ftplib.FTP() as ftp:
        ftp.connect(host=host, port=port, timeout=30)
        ftp.login(user=username, passwd=password)
        ftp.set_pasv(passive)

        # Ensure the destination folder exists before writing.
        local_path.parent.mkdir(parents=True, exist_ok=True)

        with local_path.open("wb") as destination:
            ftp.retrbinary(f"RETR {remote_path}", destination.write)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a file over FTP.")
    parser.add_argument("remote_path", help="Path to the file on the FTP server.")
    parser.add_argument(
        "local_path",
        nargs="?",
        default=None,
        help="Local path to save the file. Defaults to the basename of remote_path.",
    )
    parser.add_argument("--host", help="FTP server IP or hostname.")
    parser.add_argument("--username", help="FTP user ID.")
    parser.add_argument(
        "--password",
        help="FTP password. Leave blank to be prompted securely.",
    )
    parser.add_argument("--port", type=int, default=21, help="FTP port (default: 21).")
    parser.add_argument(
        "--no-passive",
        action="store_true",
        help="Disable passive mode if the server requires active mode.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 🔴 하드코딩된 값(FTP_HOST, FTP_USER, FTP_PASSWORD)이 있으면 사용, 없으면 입력 프롬프트
    host = prompt_if_missing(args.host or FTP_HOST, "FTP server IP/hostname: ")
    username = prompt_if_missing(args.username or FTP_USER, "FTP user ID: ")
    password = prompt_if_missing(args.password or FTP_PASSWORD, "FTP password: ", secret=True)

    remote_path = args.remote_path
    # Default local path to the basename of the remote path if not provided.
    local_path = (
        Path(args.local_path)
        if args.local_path is not None
        else Path(remote_path).name
    )

    # 🔴 하드코딩: 포트는 --port 미지정 시 FTP_PORT 사용
    port = args.port if args.port != 21 else FTP_PORT

    try:
        download_file(
            host=host,
            username=username,
            password=password,
            remote_path=remote_path,
            local_path=local_path,
            port=port,
            passive=not args.no_passive,
        )
    except ftplib.all_errors as exc:
        raise SystemExit(f"FTP download failed: {exc}") from exc

    print(f"Downloaded '{remote_path}' to '{local_path}'.")


if __name__ == "__main__":
    main()
