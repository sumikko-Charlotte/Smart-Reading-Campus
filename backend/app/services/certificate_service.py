"""电子证书 PDF 渲染。

设计取舍
--------
- **服务端渲染**：证书模板、公章、编号都在后端定死，前端拿不到可编辑的模板，
  避免学生自己 P 一张证书；下载接口按证书 ID 鉴权，链接不可猜。
- **公章是绘制出来的**，不是贴图：颜色/文字/五角星由代码生成，换学校只需改 seal_name。
- 字体走 Windows 自带中文字体，缺失时降级 Helvetica（会丢中文，健康检查里会提示）。
"""
from __future__ import annotations

import io
import math
import os

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_CANDIDATES = [
    ("SimHei", r"C:\Windows\Fonts\simhei.ttf", None),
    ("MicrosoftYaHei", r"C:\Windows\Fonts\msyh.ttc", 0),
    ("SimSun", r"C:\Windows\Fonts\simsun.ttc", 0),
]

_INK = HexColor("#2b2b2b")
_RED = HexColor("#b3121b")
_GOLD = HexColor("#b08d57")
_PAPER = HexColor("#fffdf7")

LEVEL_TITLES = {"school": "校 级", "college": "院 级", "none": ""}


def _register_fonts() -> tuple[str, str]:
    """返回 (标题字体, 正文字体)。找不到中文字体时退回 Helvetica。"""
    title_font, body_font = "Helvetica-Bold", "Helvetica"
    for name, path, index in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            kwargs = {"subfontIndex": index} if index is not None else {}
            pdfmetrics.registerFont(TTFont(name, path, **kwargs))
        except Exception:  # noqa: BLE001 - 字体损坏/被占用时继续尝试下一个
            continue
        if body_font == "Helvetica":
            body_font = name
        if title_font == "Helvetica-Bold":
            title_font = name
    return title_font, body_font


def _star(c: canvas.Canvas, cx: float, cy: float, radius: float, color: Color) -> None:
    path = c.beginPath()
    for i in range(10):
        angle = math.radians(90 + i * 36)
        r = radius if i % 2 == 0 else radius * 0.42
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    c.setFillColor(color)
    c.drawPath(path, fill=1, stroke=0)


def _draw_seal(c: canvas.Canvas, cx: float, cy: float, radius: float, seal_name: str, body_font: str) -> None:
    """绘制圆形公章：双圈 + 五角星 + 环形单位名称。"""
    c.saveState()
    c.setFillColor(_RED)
    c.setStrokeColor(_RED)
    c.setLineWidth(3)
    c.circle(cx, cy, radius, stroke=1, fill=0)
    c.setLineWidth(1)
    c.circle(cx, cy, radius - 4, stroke=1, fill=0)
    _star(c, cx, cy + radius * 0.05, radius * 0.30, _RED)

    if seal_name:
        chars = list(seal_name)
        # 从左下开始顺时针排布，留出底部缺口给编号区
        start, end = 205, -25
        step = (start - end) / max(len(chars) - 1, 1) if len(chars) > 1 else 0
        size = max(8, radius * 0.22)
        c.setFont(body_font, size)
        for index, char in enumerate(chars):
            angle = math.radians(start - index * step)
            x = cx + (radius - size * 1.05) * math.cos(angle)
            y = cy + (radius - size * 1.05) * math.sin(angle)
            c.saveState()
            c.translate(x, y)
            c.rotate(start - index * step - 90)
            c.drawCentredString(0, 0, char)
            c.restoreState()
    c.restoreState()


def _wrap(c: canvas.Canvas, text: str, font: str, size: int, max_width: float) -> list[str]:
    """按字符宽度折行（中文没有空格，只能逐字累加）。"""
    lines, current = [], ""
    for char in text:
        if c.stringWidth(current + char, font, size) <= max_width:
            current += char
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def render_certificate(
    *,
    holder_name: str,
    student_no: str,
    college: str,
    activity_title: str,
    activity_level: str,
    certificate_name: str,
    seal_name: str,
    serial_no: str,
    verify_code: str,
    issued_date: str,
) -> bytes:
    """生成证书 PDF 字节流。调用方负责鉴权与落库。"""
    title_font, body_font = _register_fonts()
    buffer = io.BytesIO()
    width, height = landscape(A4)  # 297mm x 210mm
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    c.setTitle(f"{certificate_name} - {holder_name}")
    c.setAuthor("智阅校园")

    # 纸底 + 金色外框 + 红色内框
    c.setFillColor(_PAPER)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(6)
    c.rect(12 * mm, 12 * mm, width - 24 * mm, height - 24 * mm, fill=0, stroke=1)
    c.setStrokeColor(_RED)
    c.setLineWidth(1.2)
    c.rect(16 * mm, 16 * mm, width - 32 * mm, height - 32 * mm, fill=0, stroke=1)

    # 标题
    c.setFillColor(_RED)
    c.setFont(title_font, 44)
    c.drawCentredString(width / 2, height - 52 * mm, "荣 誉 证 书")
    c.setFillColor(_GOLD)
    c.setFont(body_font, 12)
    c.drawCentredString(width / 2, height - 62 * mm, "CERTIFICATE OF HONOR")

    # 级别徽标
    level_text = LEVEL_TITLES.get(activity_level, "")
    if level_text:
        c.setFillColor(_RED)
        c.setFont(body_font, 13)
        c.drawCentredString(width / 2, height - 74 * mm, f"· {level_text} 活 动 ·")

    # 正文
    c.setFillColor(_INK)
    body_size = 16
    line_height = 12 * mm
    top = height - 96 * mm
    intro = f"兹证明  {holder_name}  同学"
    c.setFont(title_font, 22)
    c.drawCentredString(width / 2, top, intro)

    c.setFont(body_font, body_size)
    detail = f"（学号：{student_no}{'，' + college if college else ''}）"
    c.drawCentredString(width / 2, top - 12 * mm, detail)

    paragraph = (
        f"积极参与「{activity_title}」，全程投入、表现优异，"
        "展现了我校学子良好的阅读素养与精神风貌，特发此证，以资鼓励。"
    )
    lines = _wrap(c, paragraph, body_font, body_size, width - 150 * mm)
    for index, line in enumerate(lines[:4]):
        c.drawCentredString(width / 2 - 20 * mm, top - 26 * mm - index * line_height, line)

    # 落款（公章压在落款文字右上方，模拟实物盖章）
    sign_x = width - 72 * mm
    sign_y = 52 * mm
    c.setFont(body_font, 14)
    c.drawCentredString(sign_x, sign_y + 14 * mm, seal_name)
    c.drawCentredString(sign_x, sign_y + 5 * mm, issued_date)
    _draw_seal(c, width - 52 * mm, sign_y + 12 * mm, 20 * mm, seal_name, body_font)

    # 编号与验真
    c.setFillColor(HexColor("#666666"))
    c.setFont(body_font, 9)
    c.drawString(24 * mm, 26 * mm, f"证书编号：{serial_no}")
    c.drawString(24 * mm, 21 * mm, f"验真码：{verify_code}    验真入口：/certificates/verify/{verify_code}")
    c.setFillColor(_GOLD)
    c.setFont(body_font, 8)
    c.drawRightString(width - 24 * mm, 21 * mm, "智阅校园 · 高校双端协同阅读推广平台")

    c.showPage()
    c.save()
    return buffer.getvalue()
