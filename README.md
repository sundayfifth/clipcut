# clipcut

แปลงคลิป 16:9 เป็น 9:16 สำหรับ TikTok แบบกึ่งอัตโนมัติ

## ติดตั้ง

ต้องมี Python 3.12+ และ ffmpeg

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## ใช้งาน

```
source .venv/bin/activate
uvicorn app.main:app --reload
```

เปิด http://127.0.0.1:8000

## สถานะ

ยังเป็นโครงเปล่า — pipeline (ingest / analyze / plan / render / report) ยังไม่ได้เขียน
