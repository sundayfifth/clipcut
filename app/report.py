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
    # โลโก้/ลายน้ำประจำช่อง โผล่ทุกซีน รายงานรวมทีเดียวพอ
    persistent: dict[str, int] = {}
    for s in shots:
        for b in (s.get("text_boxes") or []):
            if b.get("cause") == "persistent":
                key = b["text"].strip()[:40]
                persistent[key] = persistent.get(key, 0) + 1
    lost_by_band = [
        (s, b) for s in shots for b in (s.get("text_boxes") or [])
        if b.get("lost") and b.get("cause") == "band"
    ]

    lines += ["## สรุปสิ่งที่ต้องทำ", ""]
    if not plan.get("text_detection", True):
        lines += [
            "> ⚠️ **เครื่องนี้อ่านข้อความในเฟรมไม่ได้** (ใช้ Apple Vision ซึ่งมีเฉพาะบน Mac)",
            "> รายการด้านล่างจึงไม่รวมกราฟฟิกที่อาจหายไป — ต้องเปิดคลิปตรวจเอง",
            "",
        ]
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
    # กราฟฟิกอันเดียวมักกินหลายซีน จัดกลุ่มตามข้อความ ไม่งั้นรายการยาวเกินจำเป็น
    grouped: dict[str, list[dict]] = {}
    for shot, box in lost_by_crop:
        key = box["text"].strip()[:50] or "(ไม่มีข้อความ)"
        grouped.setdefault(key, []).append(shot)

    if grouped:
        appears = sum(len({s["shot_index"] for s in v}) for v in grouped.values())
        lines.append(
            f"- [ ] **ทำกราฟฟิกใหม่ {len(grouped)} ชิ้น** "
            f"(โผล่รวม {appears} ซีน) — โดนตัดข้างจากการ crop"
        )
    if persistent:
        names = " · ".join(f"“{t}”" for t in list(persistent)[:3])
        lines.append(
            f"- [ ] **วางโลโก้ประจำช่องใหม่** — {names} หายไปจากการ crop "
            f"(โผล่ทุกซีน วางครั้งเดียวคลุมทั้งคลิปได้)"
        )
    if not bands.active and not lost_by_crop and not persistent:
        lines.append(
            "- ตรวจข้อความไม่ได้บนเครื่องนี้ ต้องเปิดคลิปดูเองว่ามีกราฟฟิกไหนหายมั้ย"
            if not plan.get("text_detection", True)
            else "- ไม่มีข้อความไหนหายไป ไม่ต้องเติมกราฟฟิก"
        )
    lines.append("")

    if grouped:
        lines += ["## กราฟฟิกที่ต้องทำใหม่", ""]
        for text, shots_with in sorted(
            grouped.items(), key=lambda kv: -len(kv[1])
        ):
            numbers = sorted({s["shot_index"] + 1 for s in shots_with})
            where = ", ".join(f"ซีน {n}" for n in numbers[:6])
            more = f" (+{len(numbers) - 6})" if len(numbers) > 6 else ""
            first = min(shots_with, key=lambda s: s["start"])
            lines.append(f"- [ ] “{text}”")
            lines.append(f"      {where}{more} · เริ่ม {_tc(first['start'])}")
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

        boxes = [b for b in (s.get("text_boxes") or []) if not b.get("persistent")]
        if not boxes:
            lines.append("- ไม่พบข้อความเฉพาะของซีนนี้")
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
