"""纯 Python 生成积分卡 PDF（不依赖 Word / WPS / 任何外部程序）。

版面与 export_to_word 输出的 docx 保持一致：
A4 210×297mm，左右边距 10mm，上下 5mm，3 列 × 7 行，单元格共用边框。
"""

import io
import os

from fpdf import FPDF

PAGE_W = 210.0
PAGE_H = 297.0
MARGIN_X = 10.0
MARGIN_Y = 5.0
COLS = 3
ROWS = 7
RESERVE_MM = 9.0            # 预留，避免表格多出一行
BORDER_MM = 0.18            # ≈0.5pt

FONT_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fonts")


def _font_dir():
    os.makedirs(FONT_CACHE, exist_ok=True)
    return FONT_CACHE


def _extract_ttc(name, index=0):
    """把 Windows 的 .ttc 字体集合里的第 index 个字体抽成 .ttf 缓存。"""
    cached = os.path.join(_font_dir(), f"{name}.ttf")
    if os.path.exists(cached):
        return cached

    windir = os.environ.get("WINDIR", r"C:\Windows")
    source = os.path.join(windir, "Fonts", f"{name}.ttc")
    if not os.path.exists(source):
        return None

    try:
        from fontTools.ttLib import TTFont
        font = TTFont(source, fontNumber=index)
        font.save(cached)
        return cached
    except Exception:
        return None


def _pick(paths):
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in paths:
        full = name if os.path.isabs(name) else os.path.join(windir, "Fonts", name)
        if os.path.exists(full):
            return full
    return None


def _register_fonts(pdf):
    """返回 (正文字体名, 等宽字体名)。"""
    song = _extract_ttc("simsun") or _pick(["Deng.ttf", "SIMLI.TTF", "simsun.ttf"])
    mono = _pick(["consola.ttf", "cour.ttf"])

    body = "body"
    if song:
        pdf.add_font(body, "", song)
    code = body
    if mono:
        pdf.add_font("mono", "", mono)
        code = "mono"
    return body, code


def _fit(pdf, text, max_width, size):
    """按最大宽度截断，超出加省略号。"""
    pdf.set_font_size(size)
    if pdf.get_string_width(text) <= max_width:
        return text
    ellipsis = "…"
    while text and pdf.get_string_width(text + ellipsis) > max_width:
        text = text[:-1]
    return text + ellipsis


def _bold_text(pdf, x, y, text, size):
    """没有粗体字重时，用极轻微的重描模拟加粗。"""
    pdf.set_font_size(size)
    pdf.text(x, y, text)
    pdf.text(x + 0.12, y, text)


def build_cards_pdf(codes, class_name, title, amount, issue_date, out_path,
                    barcode_bytes, per_page=ROWS * COLS):
    """生成卡片 PDF，返回输出路径。barcode_bytes(code) 需返回 PNG 字节。"""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(MARGIN_X, MARGIN_Y, MARGIN_X)
    body_font, code_font = _register_fonts(pdf)

    col_w = (PAGE_W - MARGIN_X * 2) / COLS
    row_h = (PAGE_H - MARGIN_Y * 2 - RESERVE_MM) / ROWS

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(BORDER_MM)
    pdf.set_text_color(0, 0, 0)

    pages = [codes[i:i + per_page] for i in range(0, len(codes), per_page)] or [[]]

    for page_index, page_codes in enumerate(pages):
        pdf.add_page()

        table_x = MARGIN_X
        table_y = MARGIN_Y

        # 外框 + 网格（相邻单元格共用一条线）
        pdf.rect(table_x, table_y, col_w * COLS, row_h * ROWS)
        for c in range(1, COLS):
            pdf.line(table_x + c * col_w, table_y,
                     table_x + c * col_w, table_y + row_h * ROWS)
        for r in range(1, ROWS):
            pdf.line(table_x, table_y + r * row_h,
                     table_x + col_w * COLS, table_y + r * row_h)

        for index, code in enumerate(page_codes):
            row = index // COLS
            col = index % COLS
            x0 = table_x + col * col_w
            y0 = table_y + row * row_h
            inner_x = x0 + 1.8
            max_w = col_w - 3.6

            pdf.set_font(body_font, "", 10)
            _bold_text(pdf, inner_x, y0 + 4.2, "班级积分卡", 10)

            # 面额（右上，16pt 加粗）
            amount_text = f"{amount}分"
            pdf.set_font_size(16)
            amount_w = pdf.get_string_width(amount_text)
            _bold_text(pdf, x0 + col_w - 2.0 - amount_w, y0 + 7.2, amount_text, 16)

            pdf.set_font(body_font, "", 9)
            pdf.text(inner_x, y0 + 9.4, _fit(pdf, f"班级：{class_name}", max_w, 9))

            date_text = f"日期：{issue_date}"
            pdf.set_font_size(9)
            date_w = pdf.get_string_width(date_text)
            title_text = _fit(pdf, f"标题：{title}", max_w - date_w - 3, 9)
            pdf.text(inner_x, y0 + 13.2, title_text)
            pdf.text(x0 + col_w - 2.0 - date_w, y0 + 13.2, date_text)

            # 条码：宽 50mm，居中；高度按原图比例算，编号排在条码下面
            png = barcode_bytes(code)
            img_w = 50.0
            img_h = img_w * 0.42
            try:
                from PIL import Image as _Image
                with _Image.open(io.BytesIO(png)) as probe:
                    img_h = img_w * probe.height / probe.width
            except Exception:
                pass

            barcode_y = y0 + 14.0
            pdf.image(io.BytesIO(png), x=x0 + (col_w - img_w) / 2, y=barcode_y, w=img_w)

            pdf.set_font(code_font, "", 8)
            code_w = pdf.get_string_width(code)
            pdf.text(x0 + (col_w - code_w) / 2, barcode_y + img_h + 3.4, code)

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    pdf.output(out_path)
    return out_path
