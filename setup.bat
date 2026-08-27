@echo off
chcp 65001 >nul
REM ติดตั้ง clipcut บน Windows — ดับเบิลคลิกไฟล์นี้ได้เลย
cd /d "%~dp0"
echo.
echo ===== ติดตั้ง clipcut =====
echo.

REM --- Python ---
set PY=
for %%C in (py python) do (
  if not defined PY (
    %%C -c "import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 1)" >nul 2>&1
    if not errorlevel 1 set PY=%%C
  )
)
if not defined PY (
  echo   [x] ไม่พบ Python 3.12 ขึ้นไป
  echo.
  echo   ติดตั้งก่อนที่ https://www.python.org/downloads/
  echo   ตอนติดตั้งอย่าลืมติ๊ก "Add Python to PATH"
  echo.
  pause
  exit /b 1
)
echo   [v] พบ Python แล้ว

REM --- ffmpeg ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   [x] ไม่พบ ffmpeg — กำลังลองติดตั้งด้วย winget
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  where ffmpeg >nul 2>&1
  if errorlevel 1 (
    echo.
    echo   ติดตั้ง ffmpeg ไม่สำเร็จ
    echo   โหลดเองที่ https://www.gyan.dev/ffmpeg/builds/ แล้วเพิ่มลงใน PATH
    echo   จากนั้น "ปิดหน้าต่างนี้แล้วเปิดใหม่" ก่อนรัน setup อีกครั้ง
    echo.
    pause
    exit /b 1
  )
)
echo   [v] พบ ffmpeg แล้ว

REM --- venv + แพ็กเกจ ---
echo.
echo ติดตั้งแพ็กเกจ (ครั้งแรกใช้เวลาสัก 2-5 นาที)
if not exist .venv\Scripts\python.exe %PY% -m venv .venv
if errorlevel 1 ( echo สร้าง venv ไม่สำเร็จ & pause & exit /b 1 )
.venv\Scripts\python.exe -m pip install -q --upgrade pip
.venv\Scripts\python.exe -m pip install -q -e .
if errorlevel 1 ( echo ติดตั้งแพ็กเกจไม่สำเร็จ & pause & exit /b 1 )
echo   [v] แพ็กเกจครบ

REM --- โมเดลตรวจจับคน ---
if not exist models\efficientdet_lite0.tflite (
  echo.
  echo ดาวน์โหลดโมเดลตรวจจับคน 14 MB
  if not exist models mkdir models
  curl -sSL -o models\efficientdet_lite0.tflite "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite"
  if errorlevel 1 ( echo โหลดโมเดลไม่สำเร็จ & pause & exit /b 1 )
)
echo   [v] โมเดลพร้อม

if not exist media\input mkdir media\input
if not exist media\work mkdir media\work
if not exist media\output mkdir media\output

echo.
echo ===== ติดตั้งเสร็จแล้ว =====
echo   วางคลิปไว้ใน media\input\ แล้วดับเบิลคลิก start.bat
echo.
echo   หมายเหตุ: บน Windows จะไม่มี checklist กราฟฟิก
echo   เพราะการอ่านข้อความไทยในเฟรมใช้ Apple Vision ซึ่งมีเฉพาะบน Mac
echo   ส่วนอื่นใช้ได้ครบ
echo.
pause
