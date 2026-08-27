#!/usr/bin/env bash
# ติดตั้ง clipcut บน Mac — ดับเบิลคลิกไฟล์นี้ได้เลย
set -uo pipefail
cd "$(dirname "$0")"

say()  { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  ✓ %s\n" "$1"; }
bad()  { printf "  ✗ %s\n" "$1"; }
stop() { printf "\n\033[31m%s\033[0m\n\nกด Enter เพื่อปิดหน้าต่าง"; read -r _; exit 1; }

say "ติดตั้ง clipcut"

# ── Python ──
PY=""
for c in python3.13 python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys;print(sys.version_info>=(3,12))' 2>/dev/null || echo False)
    [ "$v" = "True" ] && PY="$c" && break
  fi
done
if [ -z "$PY" ]; then
  bad "ไม่พบ Python 3.12 ขึ้นไป"
  stop "ติดตั้งก่อนที่ https://www.python.org/downloads/ แล้วรันไฟล์นี้ใหม่"
fi
ok "Python: $($PY --version)"

# ── ffmpeg ──
if ! command -v ffmpeg >/dev/null 2>&1; then
  bad "ไม่พบ ffmpeg"
  if command -v brew >/dev/null 2>&1; then
    say "กำลังติดตั้ง ffmpeg ด้วย Homebrew (อาจใช้เวลาสักครู่)"
    brew install ffmpeg || stop "ติดตั้ง ffmpeg ไม่สำเร็จ ลองรัน: brew install ffmpeg"
  else
    stop "ต้องติดตั้ง ffmpeg ก่อน — ติดตั้ง Homebrew จาก https://brew.sh แล้วรัน: brew install ffmpeg"
  fi
fi
ok "ffmpeg: $(ffmpeg -version | head -1 | cut -d' ' -f1-3)"

# ── venv + แพ็กเกจ ──
say "ติดตั้งแพ็กเกจ (ครั้งแรกใช้เวลาสัก 2-5 นาที)"
[ -d .venv ] || "$PY" -m venv .venv || stop "สร้าง venv ไม่สำเร็จ"
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -e "." || stop "ติดตั้งแพ็กเกจไม่สำเร็จ"
ok "แพ็กเกจครบ"

# ── โมเดลตรวจจับคน ──
if [ ! -f models/efficientdet_lite0.tflite ]; then
  say "ดาวน์โหลดโมเดลตรวจจับคน (14 MB)"
  ./download-models.sh || stop "โหลดโมเดลไม่สำเร็จ ตรวจอินเทอร์เน็ตแล้วลองใหม่"
fi
ok "โมเดลพร้อม"

mkdir -p media/input media/work media/output

say "ติดตั้งเสร็จแล้ว"
echo "  วางคลิปไว้ใน media/input/ แล้วดับเบิลคลิก start.command"
echo
echo "กด Enter เพื่อปิดหน้าต่าง"
read -r _
