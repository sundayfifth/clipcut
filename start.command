#!/usr/bin/env bash
# เปิด clipcut — ดับเบิลคลิกไฟล์นี้
set -uo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/uvicorn ]; then
  echo "ยังไม่ได้ติดตั้ง — ดับเบิลคลิก setup.command ก่อน"
  echo; echo "กด Enter เพื่อปิด"; read -r _; exit 1
fi

PORT=8000
# ถ้าพอร์ตไม่ว่างให้ขยับไปพอร์ตถัดไป จะได้ไม่ต้องมานั่งไล่ปิดโปรเซสเอง
while lsof -i ":$PORT" >/dev/null 2>&1; do PORT=$((PORT+1)); done

echo "เปิด clipcut ที่ http://127.0.0.1:$PORT"
echo "ปิดหน้าต่างนี้เมื่อเลิกใช้"
echo
( sleep 2; open "http://127.0.0.1:$PORT" ) &
exec ./.venv/bin/uvicorn app.main:app --port "$PORT"
