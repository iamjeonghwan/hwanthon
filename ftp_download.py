"""FTP bulk downloader by equipment master data.

마스터 데이터(eqp_id, IP, model)를 읽어와 각 장비(IP)에 모델별 FTP 계정으로
접속해, 모델별로 정해진 원격 경로/파일을 다운로드합니다.
장비 Model은 2종이며, Model별로 FTP ID/비밀번호·다운로드 대상 파일·경로가 다릅니다.
"""

# Python 3.7+ 에서 타입 힌트에 str | None 같은 문법을 쓰기 위한 선언
from __future__ import annotations

import argparse
import ftplib
import getpass
from pathlib import Path
from typing import Callable

import pandas as pd

# =============================================================================
# 🔴 하드코딩 영역 (아래 값을 실제 환경에 맞게 수정하세요)
# =============================================================================
# 마스터 데이터 파일 경로 (CSV 또는 Excel). 컬럼: eqp_id, IP, model
MASTER_DATA_PATH: str = "master_equipment.csv"  # 🔴 하드코딩: 예) "master_equipment.xlsx"

# 모델별 FTP 계정 및 다운로드 대상 경로/파일 (모델명은 마스터의 model 컬럼 값과 일치해야 함)
MODEL_CONFIG: dict[str, dict[str, str]] = {
    # 🔴 하드코딩: Model 1 장비용 계정 및 원격 파일 경로
    "Model1": {
        "ftp_user": "user_model1",       # 🔴 FTP ID
        "ftp_password": "pwd_model1",    # 🔴 FTP 비밀번호
        "remote_path": "/log/data1.txt", # 🔴 다운로드할 파일의 FTP 전체 경로
    },
    # 🔴 하드코딩: Model 2 장비용 계정 및 원격 파일 경로
    "Model2": {
        "ftp_user": "user_model2",
        "ftp_password": "pwd_model2",
        "remote_path": "/data/report.csv",
    },
}

# FTP 포트 (모델별로 다르면 여기서는 공통, 필요 시 MODEL_CONFIG에 "port" 추가 가능)
FTP_PORT: int = 21  # 🔴 하드코딩
# =============================================================================


def load_master_data(path: str | Path) -> pd.DataFrame:
    """마스터 데이터 파일(CSV 또는 Excel)을 읽어 DataFrame으로 반환합니다.
    필수 컬럼: eqp_id, IP, model.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"마스터 데이터 파일이 없습니다: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, dtype=str)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        raise ValueError(f"지원 형식: .csv, .xlsx, .xls (현재: {suffix})")

    for col in ("eqp_id", "IP", "model"):
        if col not in df.columns:
            raise ValueError(f"마스터 데이터에 '{col}' 컬럼이 없습니다. 컬럼: {list(df.columns)}")
    return df


def prompt_if_missing(value: str | None, prompt_text: str, secret: bool = False) -> str:
    """값이 있으면 그대로 반환하고, 없으면 사용자에게 prompt_text로 입력을 요청합니다.
    secret=True면 getpass로 입력해 터미널에 비밀번호가 보이지 않습니다.
    """
    if value:
        return value
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
    """FTP 서버에 접속해 remote_path 파일 하나를 local_path로 다운로드합니다.
    port: FTP 포트 (기본 21). passive: True면 수동 모드(방화벽에 유리).
    """

    # ftplib.FTP() 컨텍스트 매니저: 블록 끝에서 연결 자동 종료
    with ftplib.FTP() as ftp:
        # TCP 연결 (호스트, 포트, 30초 타임아웃)
        ftp.connect(host=host, port=port, timeout=30)
        # 로그인 (사용자명, 비밀번호)
        ftp.login(user=username, passwd=password)
        # 수동 모드 설정 (클라이언트가 데이터 포트를 열고 서버가 접속)

        # 저장할 로컬 경로의 부모 폴더가 없으면 생성 (parents=True로 상위 경로까지)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # 로컬 파일을 바이너리 쓰기 모드로 열고, FTP RETR 명령으로 받은 데이터를 씀
        with local_path.open("wb") as destination:
            ftp.retrbinary(f"RETR {remote_path}", destination.write)


def parse_args() -> argparse.Namespace:
    """명령줄 인자를 파싱해 argparse.Namespace 객체로 반환합니다."""

    parser = argparse.ArgumentParser(
        description="마스터 데이터(eqp_id, IP, model) 기준으로 여러 장비에 FTP 접속해 모델별 파일을 다운로드합니다."
    )
    # 마스터 데이터 파일 경로 (CSV/Excel, 컬럼: eqp_id, IP, model)
    parser.add_argument(
        "--master",
        "-m",
        default=MASTER_DATA_PATH,
        help=f"마스터 데이터 파일 경로 (기본: {MASTER_DATA_PATH})",
    )
    # 다운로드 파일을 저장할 루트 폴더 (장비별로 eqp_id 하위에 저장)
    parser.add_argument(
        "--output-dir",
        "-o",
        default="downloads",
        help="다운로드 저장 루트 디렉터리 (기본: downloads)",
    )
    parser.add_argument("--port", type=int, default=FTP_PORT, help="FTP 포트 (기본값: 21).")
    parser.add_argument(
        "--no-passive",
        action="store_true",
        help="수동 모드 비활성화 (서버가 능동 모드를 요구할 때 사용).",
    )

    return parser.parse_args()


def main() -> None:
    """마스터 데이터를 읽어 각 장비(IP)에 모델별 계정으로 접속해 파일을 다운로드합니다."""

    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 마스터 데이터 로드 (eqp_id, IP, model 컬럼 필수)
    try:
        master = load_master_data(args.master)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(e) from e

    success_count = 0
    fail_count = 0

    for idx, row in master.iterrows():
        eqp_id = str(row["eqp_id"]).strip()
        host = str(row["IP"]).strip()
        model = str(row["model"]).strip()

        if not host or not model:
            print(f"[건너뜀] eqp_id={eqp_id}: IP 또는 model 비어 있음")
            fail_count += 1
            continue

        # 모델별 설정 조회 (MODEL_CONFIG에 해당 model이 있어야 함)
        if model not in MODEL_CONFIG:
            print(f"[실패] eqp_id={eqp_id}, IP={host}: 알 수 없는 model '{model}' (설정: {list(MODEL_CONFIG.keys())})")
            fail_count += 1
            continue

        cfg = MODEL_CONFIG[model]
        username = cfg["ftp_user"]
        password = cfg["ftp_password"]
        remote_path = cfg["remote_path"]
        # 장비별로 eqp_id 폴더를 만들고, 원격 파일명으로 저장
        local_path = output_dir / eqp_id / Path(remote_path).name

        try:
            download_file(
                host=host,
                username=username,
                password=password,
                remote_path=remote_path,
                local_path=local_path,
                port=args.port,
                passive=not args.no_passive,
            )
            print(f"[성공] eqp_id={eqp_id}, IP={host}, model={model} -> {local_path}")
            success_count += 1
        except ftplib.all_errors as exc:
            print(f"[실패] eqp_id={eqp_id}, IP={host}: {exc}")
            fail_count += 1

    print(f"\n완료: 성공 {success_count}건, 실패 {fail_count}건")


# 이 파일을 직접 실행했을 때만 main() 호출 (import 시에는 호출 안 함)
if __name__ == "__main__":
    main()
