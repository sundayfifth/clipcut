"""checklist บอกว่าคลิปนี้ต้องไปเติมกราฟฟิกอะไรบ้าง

ไม่ได้ทำกราฟฟิกให้ — แต่ชี้ว่า *ข้อความไหน* หายไปเพราะอะไร พร้อมข้อความจริง
ที่อ่านได้จากเฟรม เพื่อให้คนตัดต่อทำใหม่ใน CapCut ได้โดยไม่ต้องเปิดคลิปไล่ดูเอง

แยกสาเหตุการหาย 2 แบบ เพราะต้องจัดการคนละอย่าง:
- band = โดนตัดแถบบน/ล่าง มักเป็นซับกับโลโก้ ซึ่งตั้งใจตัดอยู่แล้ว
- crop = โดนตัดข้างซ้าย/ขวา คือกราฟฟิกที่ต้องทำใหม่จริงๆ
"""

from __future__ import annotations

from app.bands import Bands


def _tc(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def _where(box: dict) -> str:
    cy = (box["y0"] + box["y1"]) / 2
    cx = (box["x0"] + box["x1"]) / 2
    vert = "บน" if cy < 0.33 else "ล่าง" if cy > 0.66 else "กลาง"
    horiz = "ซ้าย" if cx < 0.33 else "ขวา" if cx > 0.66 else "กลาง"
    return f"{vert}-{horiz}"


def build_checklist(plan: dict) -> str:
    bands = Bands.from_dict(plan.get("bands"))
    shots = [s for s in plan["shots"] if s.get("included", True)]
    skipped = [s for s in plan["shots"] if not s.get("included", True)]
    src = plan["source_size"]

    lines = [
        f"# กราฟฟิกที่ต้องเติม — {plan['source']}",
        "",
        f"ต้นฉบับ {src['width']}x{src['height']} · ใช้ {len(shots)} ซีน "
        f"(ข้าม {len(skipped)} ซีน) · ยาวรวม {plan['summary']['duration']} วิ",
        "",
    ]

    lost_by_crop = [
        (s, b) for s in shots for b in (s.get("text_boxes") or [])
        if b.get("lost") and b.get("cause") == "crop"
    ]
    lost_by_band = [
        (s, b) for s in shots for b in (s.get("text_boxes") or [])
        if b.get("lost") and b.get("cause") == "band"
    ]

    lines += ["## สรุปสิ่งที่ต้องทำ", ""]
    if bands.active:
        what = "ตัดทิ้ง" if bands.mode == "trim" else "เบลอทับ"
        parts = []
        if bands.top:
            parts.append(f"บน {bands.top:.0%}")
        if bands.bottom:
            parts.append(f"ล่าง {bands.bottom:.0%}")
        lines.append(
            f"- [ ] **ใส่ซับใหม่** — แถบ{' และ '.join(parts)}ถูก{what}ทั้งคลิป "
            f"(ใช้ skill `subtitle-align`)"
        )
    if lost_by_crop:
        lines.append(
            f"- [ ] **ทำกราฟฟิกใหม่ {len(lost_by_crop)} จุด** — โดนตัดข้างจากการ crop "
            f"ดูรายการด้านล่าง"
        )
    if not bands.active and not lost_by_crop:
        lines.append("- ไม่มีข้อความไหนหายไป ไม่ต้องเติมกราฟฟิก")
    lines.append("")

    if lost_by_crop:
        lines += ["## ข้อความที่หายเพราะโดน crop ข้าง", ""]
        for shot, box in lost_by_crop:
            lines.append(
                f"- [ ] ซีน {shot['shot_index'] + 1} · {_tc(shot['start'])} "
                f"· {_where(box)} · เหลือ {box['kept']:.0%} — “{box['text']}”"
            )
        lines.append("")

    if lost_by_band:
        seen: set[str] = set()
        uniq = []
        for shot, box in lost_by_band:
            key = box["text"].strip()[:40]
            if key and key not in seen:
                seen.add(key)
                uniq.append((shot, box))
        lines += [
            "## ข้อความที่หายเพราะตัดแถบ (ตั้งใจตัด)", "",
            "ส่วนใหญ่คือซับกับโลโก้ ถ้าอันไหนไม่ใช่ซับ ต้องทำใหม่ด้วย", "",
        ]
        for shot, box in uniq[:20]:
            lines.append(
                f"- ซีน {shot['shot_index'] + 1} · {_where(box)} — “{box['text'][:60]}”"
            )
        if len(uniq) > 20:
            lines.append(f"- _(อีก {len(uniq) - 20} รายการ)_")
        lines.append("")

    lines += ["## รายซีน", ""]
    for s in shots:
        n = s["shot_index"] + 1
        lines.append(f"### ซีน {n} · {_tc(s['start'])} → {_tc(s['end'])} · {s['mode']}")
        lines.append("")

        if s["mode"] == "crop":
            crop = s["crop"]
            cut_left = crop["x"]
            cut_right = src["width"] - crop["x"] - crop["w"]
            moving = (s.get("path") or {}).get("kind") == "poly"
            lines.append(
                f"- ตัดข้างซ้าย {cut_left}px ข้างขวา {cut_right}px"
                + (" (กรอบขยับตามคน)" if moving else "")
            )
        else:
            lines.append("- ย่อทั้งเฟรม เติมพื้นหลังเบลอบน-ล่าง ไม่มีอะไรถูกตัดข้าง")

        boxes = s.get("text_boxes") or []
        if not boxes:
            lines.append("- ไม่พบข้อความในซีนนี้")
        for box in boxes:
            state = (
                "❌ หาย" if box.get("lost")
                else "⚠️ โดนตัดบางส่วน" if box.get("kept", 1) < 0.95
                else "✅ อยู่ครบ"
            )
            lines.append(f"- {state} · {_where(box)} — “{box['text'][:60]}”")

        if s["confidence"] < 0.5 and s["mode"] == "crop":
            lines.append("- ⚠️ เห็นคนไม่ชัด การจัดกรอบอาจไม่แม่น")
        lines.append("")

    if skipped:
        lines += ["## ซีนที่ข้ามไป", ""]
        for s in skipped:
            note = " — มีคนพูด ประโยคอาจขาด" if s.get("has_speech") else ""
            lines.append(
                f"- ซีน {s['shot_index'] + 1} · {_tc(s['start'])} → {_tc(s['end'])}{note}"
            )
        lines.append("")

    return "\n".join(lines)
