"""checklist บอกว่าคลิปนี้ต้องไปเติมกราฟฟิกอะไรบ้าง

เครื่องมือไม่ได้ทำกราฟฟิกให้ — แค่ชี้ว่าจุดไหนของเดิมหายไป เพื่อให้คนตัดต่อ
ไปทำใหม่ใน CapCut ได้โดยไม่ต้องนั่งไล่ดูคลิปเองอีกรอบ
"""

from __future__ import annotations

from pathlib import Path

from app.bands import Bands


def _tc(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


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

    if bands.active:
        what = "ตัดทิ้ง" if bands.mode == "trim" else "เบลอทับ"
        parts = []
        if bands.top:
            parts.append(f"บน {bands.top:.0%}")
        if bands.bottom:
            parts.append(f"ล่าง {bands.bottom:.0%}")
        lines += [
            "## ทั้งคลิป",
            "",
            f"- [ ] **ซับไตเติล** — แถบ{' และ '.join(parts)}ถูก{what}ทั้งคลิป "
            f"ต้องใส่ซับใหม่ (ใช้ skill `subtitle-align`)",
        ]
        if bands.top:
            lines.append("- [ ] **โลโก้** — แถบบนถูกตัด/เบลอ ถ้าเดิมมีโลโก้ตรงนั้นต้องวางใหม่")
        lines.append("")

    lines += ["## รายซีน", ""]
    for s in shots:
        n = s["shot_index"] + 1
        head = f"### ซีน {n} · {_tc(s['start'])} → {_tc(s['end'])} · {s['mode']}"
        lines.append(head)
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
            lines.append(
                "- [ ] ถ้าเดิมมี text/graphic อยู่ริมซ้ายหรือขวา จะหายไป — ตรวจแล้วทำใหม่"
            )
        else:
            lines.append("- ย่อทั้งเฟรม เติมพื้นหลังเบลอบน-ล่าง ไม่มีอะไรถูกตัดข้าง")
            lines.append(
                "- [ ] text/graphic เดิมยังอยู่ครบแต่ **เล็กลง** — ตรวจว่าอ่านออกบนมือถือมั้ย"
            )

        if s["confidence"] < 0.5 and s["mode"] == "crop":
            lines.append(f"- ⚠️ เจอคนแค่ {s['confidence']:.0%} ของเฟรม การจัดกรอบอาจไม่แม่น")
        lines.append("")

    if skipped:
        lines += ["## ซีนที่ข้ามไป", ""]
        for s in skipped:
            lines.append(f"- ซีน {s['shot_index'] + 1} · {_tc(s['start'])} → {_tc(s['end'])}")
        lines.append("")

    return "\n".join(lines)
