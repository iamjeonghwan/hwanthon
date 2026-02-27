@echo off
REM ===== 설정 부분 =====
REM 모니터링할 EXE 파일 이름 (파일명만)
set "PROC_NAME=abc.exe"

REM 로그 파일 경로
set "LOG_DIR=C:\logs"
set "LOG_FILE=%LOG_DIR%\abc_monitor.log"

REM FTP 설정
set "FTP_HOST=리눅스서버주소또는IP"
set "FTP_USER=ftp아이디"
set "FTP_PASS=ftp비밀번호"
set "FTP_REMOTE_DIR=/원하는/리눅스/경로"

REM ===== 폴더 준비 =====
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

REM ===== 프로세스 동작 여부 확인 =====
tasklist /FI "IMAGENAME eq %PROC_NAME%" 2>NUL | find /I "%PROC_NAME%" >NUL

if "%ERRORLEVEL%"=="0" (
    set "STATUS=동작중이다"
) else (
    set "STATUS=동작중이 아니다"
)

REM ===== 로그 작성 (날짜/시간 + 상태) =====
echo %date% %time% - %PROC_NAME% %STATUS% >> "%LOG_FILE%"

REM ===== FTP 스크립트 파일 생성 =====
set "FTP_SCRIPT=%LOG_DIR%\ftp_script.txt"

> "%FTP_SCRIPT%" echo open %FTP_HOST%
>> "%FTP_SCRIPT%" echo %FTP_USER%
>> "%FTP_SCRIPT%" echo %FTP_PASS%
>> "%FTP_SCRIPT%" echo binary

if not "%FTP_REMOTE_DIR%"=="" (
    >> "%FTP_SCRIPT%" echo cd %FTP_REMOTE_DIR%
)

>> "%FTP_SCRIPT%" echo put "%LOG_FILE%"
>> "%FTP_SCRIPT%" echo bye

REM ===== FTP 실행 =====
ftp -s:"%FTP_SCRIPT%"

del "%FTP_SCRIPT%" >NUL 2>&1
