# clipcut

แปลงคลิป 16:9 เป็น 9:16 สำหรับ TikTok แบบกึ่งอัตโนมัติ

## ติดตั้ง

ต้องมี Python 3.12+ และ ffmpeg

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./download-models.sh
```

## ใช้งาน

```
source .venv/bin/activate
uvicorn app.main:app --reload
```

เปิด http://127.0.0.1:8000

## สถานะ

ทำได้แล้ว: เลือกคลิป → แบ่งซีน → ตรวจจับตัวคน → ตัดสิน crop/ย่อ+เติมพื้นหลังต่อซีน (พลิกเองได้) → render เป็น mp4 9:16

ยังไม่ได้ทำ: checklist กราฟฟิกที่ต้องเติม, ซับไตเติล (ใช้ skill `subtitle-align` แยก), ตัดสั้นเฉพาะช่วงน่าสนใจ, รับ URL YouTube
