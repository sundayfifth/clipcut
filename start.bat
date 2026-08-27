@echo off
chcp 65001 >nul
REM เปิด clipcut — ดับเบิลคลิกไฟล์นี้
cd /d "%~dp0"

if not exist .venv\Scripts\uvicorn.exe (
  echo ยังไม่ได้ติดตั้ง — ดับเบิลคลิก setup.bat ก่อน
  pause
  exit /b 1
)

echo เปิด clipcut ที่ http://127.0.0.1:8000
echo ปิดหน้าต่างนี้เมื่อเลิกใช้
echo.
start "" http://127.0.0.1:8000
.venv\Scripts\uvicorn.exe app.main:app --port 8000
