"""
봇 아이콘 생성 스크립트.
실행: python icon_gen.py
결과: bot.ico (256x256 포함 멀티 사이즈)
"""
from PIL import Image, ImageDraw, ImageFont
import os

SIZE = 256


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 배경 — 둥근 사각형 (진한 네이비)
    bg_color = (15, 20, 40, 255)
    _rounded_rect(d, 0, 0, SIZE, SIZE, radius=48, fill=bg_color)

    # 캔들스틱 차트 그리기
    # PIL y좌표: 위=0, 아래=256
    # (x중심, 몸통_y시작(작은값), 몸통_y끝(큰값), 꼬리_y시작(작은값), 꼬리_y끝(큰값), 색상)
    candles = [
        (45,  155, 190, 145, 200, "#e74c3c"),   # 음봉
        (78,  145, 178, 136, 186, "#e74c3c"),   # 음봉
        (111, 115, 148, 107, 156, "#2ecc71"),   # 양봉
        (144,  85, 118,  77, 126, "#2ecc71"),   # 양봉
        (177,  62,  92,  54, 100, "#2ecc71"),   # 양봉
        (210,  44,  72,  36,  80, "#FF6B35"),   # 양봉 (주황)
    ]

    for cx, body_y0, body_y1, wick_y0, wick_y1, color in candles:
        d.line([(cx, wick_y0), (cx, wick_y1)], fill=color, width=2)
        d.rectangle([cx - 9, body_y0, cx + 9, body_y1], fill=color)

    # 우상향 추세선
    d.line([(30, 205), (220, 60)], fill="#FF6B35", width=2)

    # "AUTO" 텍스트
    try:
        font = ImageFont.truetype("arialbd.ttf", 30)
    except Exception:
        font = ImageFont.load_default()

    text = "AUTO"
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = (SIZE - tw) // 2
    d.text((tx, 212), text, fill="#FF6B35", font=font)

    return img


def _rounded_rect(draw, x1, y1, x2, y2, radius, fill):
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


if __name__ == "__main__":
    base = draw_icon()

    # 멀티 사이즈 ICO (16, 32, 48, 64, 128, 256)
    sizes = [16, 32, 48, 64, 128, 256]
    images = [base.resize((s, s), Image.LANCZOS) for s in sizes]

    out_path = os.path.join(os.path.dirname(__file__), "bot.ico")
    images[0].save(out_path, format="ICO", sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    print(f"아이콘 생성 완료: {out_path}")
