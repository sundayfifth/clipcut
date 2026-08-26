"""จัดการแถบซับ/โลโก้ที่ burn มากับคลิปต้นฉบับ

คลิปจากช่องเดียวกัน ใช้เทมเพลตเดียวกันทั้งช่อง — ซับอยู่ล่างสุด โลโก้อยู่ขวาบน
ตำแหน่งเดิมทุกคลิป ตั้งครั้งเดียวใช้ได้ทั้งชุด

2 โหมด:
- trim  ตัดแถบทิ้งก่อน crop — สนิทที่สุด ไม่มีร่องรอย และทำให้ crop เนียนขึ้นด้วย
        เพราะกรอบ 9:16 ไปเกาะตัวคนได้ดีขึ้น แลกกับเสียภาพส่วนนั้นไป
- blur  เบลอทับเฉพาะแถบ เก็บกรอบภาพไว้เท่าเดิม แต่ยังเห็นร่องรอยเบลอ
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

MODES = ("trim", "blur")
BAND_BLUR_SIGMA = 18


@dataclass
class Bands:
    top: float = 0.0     # สัดส่วนของความสูงเฟรม 0.0-0.45
    bottom: float = 0.0
    mode: str = "trim"

    def __post_init__(self) -> None:
        self.top = _clamp(self.top)
        self.bottom = _clamp(self.bottom)
        if self.mode not in MODES:
            raise ValueError(f"โหมด '{self.mode}' ไม่ถูกต้อง (ใช้ได้: {', '.join(MODES)})")

    @property
    def active(self) -> bool:
        return self.top > 0 or self.bottom > 0

    def top_px(self, height: int) -> int:
        return int(round(height * self.top))

    def bottom_px(self, height: int) -> int:
        return int(round(height * self.bottom))

    def effective_height(self, height: int) -> int:
        """ความสูงที่เหลือให้ใช้คำนวณกรอบ — โหมด blur ไม่ได้ตัดอะไรออก"""
        if self.mode != "trim" or not self.active:
            return height
        return max(1, height - self.top_px(height) - self.bottom_px(height))

    def offset_y(self, height: int) -> int:
        return self.top_px(height) if self.mode == "trim" else 0

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Bands":
        if not data:
            return cls()
        return cls(
            top=float(data.get("top", 0.0)),
            bottom=float(data.get("bottom", 0.0)),
            mode=str(data.get("mode", "trim")),
        )


def _clamp(value: float) -> float:
    # เกิน 45% ต่อด้านแปลว่าตั้งผิด ไม่ใช่แถบซับแล้ว
    return max(0.0, min(0.45, float(value)))


def band_filter(bands: Bands, width: int, height: int) -> str | None:
    """filter ที่ต้องใส่ก่อนขั้น crop/pad — None ถ้าไม่ต้องทำอะไร"""
    if not bands.active:
        return None

    top, bottom = bands.top_px(height), bands.bottom_px(height)

    if bands.mode == "trim":
        return f"crop={width}:{height - top - bottom}:0:{top}"

    # blur: เบลอเฉพาะแถบแล้ววางทับที่เดิม
    parts = []
    labels = []
    for name, y, h in (("t", 0, top), ("b", height - bottom, bottom)):
        if h > 0:
            parts.append(
                f"[base{name}]crop={width}:{h}:0:{y},gblur=sigma={BAND_BLUR_SIGMA}[blur{name}]"
            )
            labels.append((name, y))

    if not labels:
        return None

    splits = "".join(f"[base{n}]" for n, _ in labels)
    chain = f"split={len(labels) + 1}[keep]{splits};" + ";".join(parts)
    prev = "[keep]"
    for i, (name, y) in enumerate(labels):
        out = f"[ov{i}]" if i < len(labels) - 1 else ""
        chain += f";{prev}[blur{name}]overlay=0:{y}{out}"
        prev = f"[ov{i}]"
    return chain
