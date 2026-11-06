from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
import sqlite3
import json
import hashlib
import datetime
import os
import io
import re
import time
import threading
import zipfile
import secrets
import string
import barcode
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from lxml import etree

app = FastAPI()

# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置静态文件
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 提供logo.ico文件访问
@app.get("/logo.ico")
async def get_logo():
    logo_path = os.path.join(BASE_DIR, "logo.ico")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Logo not found")

# 配置Jinja2模板（直接使用，绕过starlette缓存的bug）
template_env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")), autoescape=True)

def render(request: Request, template_name: str, context: dict = None) -> HTMLResponse:
    """渲染模板，自动注入 CSRF token 并禁用缓存（避免登录态页面被浏览器缓存）。"""
    template = template_env.get_template(template_name)
    ctx = dict(context or {})
    ctx.setdefault("csrf_token", getattr(request.state, "csrf_token", ""))
    html = template.render(**ctx)
    return HTMLResponse(html, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "X-Content-Type-Options": "nosniff",
    })

# ==================== 安全基础：会话 / CSRF / 口令哈希 ====================

SESSION_COOKIE = "session_id"
CSRF_COOKIE = "csrf_token"
SESSION_TTL = 8 * 3600            # 会话空闲 8 小时过期
MAX_QUANTITY = 500                # 单次批量生成上限
PBKDF2_ROUNDS = 200_000

# 打印排版常量：每页 3 列 × 7 行 = 21 张卡片。
# （config.json 里旧的 printing 段从未被读取，已从默认配置移除，改版式请改这里。）
CARD_COLUMNS_PER_PAGE = 3
CARD_ROWS_PER_PAGE = 7
CARD_COLUMN_WIDTH_CM = 6.0
CARD_ROW_HEIGHT_TWIP = '2131'     # 约 3.76cm，exact 固定行高

# 会话存储（简单内存存储，生产环境应使用Redis等）
# sid -> {"user": str, "expires": float, "gen": dict, "verify": dict, "setting": str}
sessions = {}

# 登录失败节流：ip -> {"count", "first_ts", "locked_until"}
_login_failures = {}
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 300


def hash_password(password: str) -> str:
    """PBKDF2-SHA256 加盐哈希，形如 pbkdf2_sha256$轮数$盐$摘要。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str):
    """返回 (是否匹配, 是否需要升级存储格式)。兼容历史明文口令，登录成功后自动升级。"""
    if not stored:
        return False, False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt, digest = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(rounds))
        except (ValueError, TypeError):
            return False, False
        return secrets.compare_digest(dk.hex(), digest), False
    # 旧版明文存储：比对成功即提示调用方升级为哈希
    return secrets.compare_digest(password.encode("utf-8"), stored.encode("utf-8")), True


def _prune_sessions():
    now = time.time()
    for sid in [s for s, v in sessions.items() if v.get("expires", 0) <= now]:
        sessions.pop(sid, None)


def get_session(request: Request):
    """返回 (sid, session)；未登录或已过期返回 (None, None)。滑动续期。"""
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None, None
    sess = sessions.get(sid)
    if not sess:
        return None, None
    if sess.get("expires", 0) <= time.time():
        sessions.pop(sid, None)
        return None, None
    sess["expires"] = time.time() + SESSION_TTL
    return sid, sess


def check_csrf(request: Request, token: str):
    expected = getattr(request.state, "csrf_token", "")
    if not expected or not token or not secrets.compare_digest(expected.encode("utf-8"), token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="CSRF 校验失败，请刷新页面后重试")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_wait_seconds(ip: str) -> int:
    rec = _login_failures.get(ip)
    if not rec:
        return 0
    left = rec.get("locked_until", 0) - time.time()
    return int(left) + 1 if left > 0 else 0


def _note_login_failure(ip: str) -> None:
    now = time.time()
    rec = _login_failures.get(ip)
    if not rec or now - rec.get("first_ts", 0) > LOGIN_LOCK_SECONDS:
        rec = {"count": 0, "first_ts": now, "locked_until": 0}
    rec["count"] += 1
    if rec["count"] >= LOGIN_MAX_FAILURES:
        rec["locked_until"] = now + LOGIN_LOCK_SECONDS
        rec["count"] = 0
        rec["first_ts"] = now
    _login_failures[ip] = rec
    # 防止字典无界增长
    if len(_login_failures) > 5000:
        for k in [k for k, v in _login_failures.items() if v.get("locked_until", 0) <= now][:2500]:
            _login_failures.pop(k, None)


def _clear_login_failures(ip: str) -> None:
    _login_failures.pop(ip, None)


def _is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or proto.split(",")[0].strip() == "https"

# 默认配置
def get_default_config():
    """返回默认配置，init_required=True，确保首次启动走管理员设置流程"""
    return {
        "system": {
            "name": "班级积分管理系统",
            "init_required": True,
            "encryption_salt": secrets.token_hex(16)
        },
        "paths": {
            "database": "./data/db/scores.db",
            "output": "./data/output"
        },
        "admin": {
            "username": "",
            "password": ""
        },
        "backup": {
            "interval_hours": 24,
            "keep": 10
        },
        "desktop": {
            "autostart": False
        },
        "print": {
            "printer": ""
        }
    }

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")

# 配置文件路径
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

# 确保数据目录存在
def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

# 读取配置文件（不存在则自动创建默认配置）
def read_config():
    ensure_data_dir()
    if not os.path.exists(CONFIG_PATH):
        # 配置文件不存在，创建默认配置并要求初始化管理员
        default_config = get_default_config()
        write_config(default_config)
        return default_config
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 深合并且只补缺失键：老版本/手改过的 config 缺少 section 时不再 KeyError，
    # 也不会覆盖用户已设置的值（尤其 init_required=False）。
    default = get_default_config()
    changed = False
    for key, val in default.items():
        if key not in config:
            config[key] = val
            changed = True
        elif isinstance(val, dict) and isinstance(config[key], dict):
            for k2, v2 in val.items():
                if k2 not in config[key]:
                    config[key][k2] = v2
                    changed = True
    if not config.get("system", {}).get("encryption_salt"):
        config["system"]["encryption_salt"] = secrets.token_hex(16)
        changed = True
    if changed:
        write_config(config)
    return config

# 写入配置文件
def write_config(config):
    ensure_data_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# 获取数据库绝对路径
def get_db_path():
    config = read_config()
    db_path = config["paths"]["database"]
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, db_path)
    return db_path

# ==================== 备份 / 清理 ====================

BACKUP_PREFIX = "classscore-backup-"
MAX_BACKUP_HOURS = 24 * 30      # 定时备份最长间隔 30 天
MAX_BACKUP_KEEP = 200


def get_backup_dir():
    path = os.path.join(DATA_DIR, "backups")
    os.makedirs(path, exist_ok=True)
    return path


def list_backups():
    """按时间升序返回备份文件名。"""
    directory = get_backup_dir()
    files = [f for f in os.listdir(directory)
             if f.startswith(BACKUP_PREFIX) and f.endswith(".zip")]
    return sorted(files)


def last_backup_time():
    files = list_backups()
    if not files:
        return None
    path = os.path.join(get_backup_dir(), files[-1])
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")


def create_backup():
    """把配置和数据库打包成一个 zip，并清理超出保留份数的旧备份。"""
    directory = get_backup_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(directory, f"{BACKUP_PREFIX}{stamp}.zip")

    db_path = get_db_path()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(CONFIG_PATH):
            zf.write(CONFIG_PATH, "config.json")
        if os.path.exists(db_path):
            zf.write(db_path, "db/scores.db")

    prune_backups()
    return os.path.basename(target)


def prune_backups():
    try:
        keep = int(read_config().get("backup", {}).get("keep", 10) or 0)
    except (TypeError, ValueError):
        keep = 10
    if keep <= 0:
        return
    files = list_backups()
    for name in files[:-keep]:
        try:
            os.remove(os.path.join(get_backup_dir(), name))
        except OSError:
            pass


def _backup_loop():
    """后台线程：按配置的间隔自动备份（interval_hours<=0 表示关闭）。"""
    while True:
        try:
            hours = float(read_config().get("backup", {}).get("interval_hours", 24) or 0)
            if hours > 0:
                files = list_backups()
                last = os.path.getmtime(os.path.join(get_backup_dir(), files[-1])) if files else 0
                if time.time() - last >= hours * 3600:
                    create_backup()
        except Exception:
            pass
        time.sleep(60)


def start_backup_scheduler():
    thread = threading.Thread(target=_backup_loop, daemon=True, name="backup-scheduler")
    thread.start()


def output_stats():
    """导出目录里的 Word 文件数量与总大小。"""
    out = get_output_dir()
    if not os.path.isdir(out):
        return 0, 0
    files = [f for f in os.listdir(out) if f.lower().endswith(".docx")]
    size = 0
    for f in files:
        try:
            size += os.path.getsize(os.path.join(out, f))
        except OSError:
            pass
    return len(files), size


def clean_output():
    out = get_output_dir()
    removed, freed = 0, 0
    if not os.path.isdir(out):
        return removed, freed
    for name in os.listdir(out):
        path = os.path.join(out, name)
        if not os.path.isfile(path) or not name.lower().endswith(".docx"):
            continue
        try:
            freed += os.path.getsize(path)
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed, freed


JUNK_SKIP_DIRS = {"python", "data", ".git", "node_modules"}


def junk_targets():
    """返回可清理的垃圾路径：__pycache__ 目录、*.pyc、*.tmp。"""
    targets = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in JUNK_SKIP_DIRS]
        if os.path.basename(root) == "__pycache__":
            targets.append(root)
            dirs[:] = []
            continue
        for name in files:
            if name.endswith((".pyc", ".pyo", ".tmp")):
                targets.append(os.path.join(root, name))
    return targets


def junk_stats():
    targets = junk_targets()
    size = 0
    for path in targets:
        if os.path.isfile(path):
            try:
                size += os.path.getsize(path)
            except OSError:
                pass
    return len(targets), size


def clean_junk():
    removed, freed = 0, 0
    for path in junk_targets():
        try:
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
            else:
                freed += os.path.getsize(path)
                os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed, freed


_dpi_ready = False


def _enable_dpi_awareness():
    """让 Tk 对话框按真实 DPI 渲染，否则 150% 缩放下会被系统位图放大而发糊。"""
    global _dpi_ready
    if _dpi_ready or os.name != "nt":
        return
    _dpi_ready = True
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)   # Per-Monitor V2
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)           # Per-Monitor
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def list_printers():
    """返回 (打印机名列表, 系统默认打印机)。非 Windows 返回空。"""
    if os.name != "nt":
        return [], ""
    try:
        import ctypes
        from ctypes import wintypes

        winspool = ctypes.WinDLL("winspool.drv")

        default = ""
        size = wintypes.DWORD(0)
        winspool.GetDefaultPrinterW(None, ctypes.byref(size))
        if size.value:
            buf = ctypes.create_unicode_buffer(size.value)
            if winspool.GetDefaultPrinterW(buf, ctypes.byref(size)):
                default = buf.value or ""

        class PRINTER_INFO_4(ctypes.Structure):
            _fields_ = [
                ("pPrinterName", wintypes.LPWSTR),
                ("pServerName", wintypes.LPWSTR),
                ("Attributes", wintypes.DWORD),
            ]

        needed, returned = wintypes.DWORD(0), wintypes.DWORD(0)
        winspool.EnumPrintersW(6, None, 4, None, 0,
                               ctypes.byref(needed), ctypes.byref(returned))
        names = []
        if needed.value:
            buf = ctypes.create_string_buffer(needed.value)
            ok = winspool.EnumPrintersW(6, None, 4, buf, needed.value,
                                        ctypes.byref(needed), ctypes.byref(returned))
            if ok:
                arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4 * returned.value)).contents
                names = [arr[i].pPrinterName for i in range(returned.value)]
        return [n for n in names if n], default
    except Exception:
        return [], ""


def _set_default_printer(name):
    try:
        import ctypes
        return bool(ctypes.WinDLL("winspool.drv").SetDefaultPrinterW(name))
    except Exception:
        return False


def send_to_printer(filepath, printer=""):
    """打印 docx；printer 为空则用系统默认打印机。返回实际使用的打印机名。"""
    if os.name != "nt":
        raise OSError("仅支持 Windows 打印")

    names, default = list_printers()
    target = printer or default

    if not printer:
        os.startfile(filepath, "print")
        return target or "系统默认打印机"

    # 指定打印机：优先用 printto 动词，失败则临时改默认打印机再还原
    try:
        import ctypes
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "printto", filepath, f'"{printer}"', None, 0)
        if rc > 32:
            return target
    except Exception:
        pass

    original = default
    if not _set_default_printer(printer):
        raise OSError(f"无法切换到打印机：{printer}")
    try:
        os.startfile(filepath, "print")
    finally:
        if original:
            _set_default_printer(original)
    return target


def pick_folder(title="选择文件夹"):
    """弹出系统文件夹选择框。

    返回：
      - 选中路径（str）
      - ""   用户主动取消
      - None 对话框打不开（环境问题）
    """
    _enable_dpi_awareness()
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            icon = os.path.join(BASE_DIR, "logo.ico")
            if os.path.exists(icon):
                root.iconbitmap(icon)
        except Exception:
            pass
        root.attributes("-topmost", True)
        root.update()
        path = filedialog.askdirectory(title=title, mustexist=True, parent=root)
        root.destroy()
    except Exception:
        return None
    return path or ""


def find_legacy_databases(folder, max_depth=4):
    """在旧版安装目录里递归找 scores.db，返回 [(path, rows, mtime)]，按记录数降序。"""
    results = []
    base = os.path.abspath(folder).rstrip(os.sep)
    for root, dirs, files in os.walk(base):
        depth = root[len(base):].count(os.sep)
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "node_modules"}]
        for name in files:
            if name.lower() != "scores.db":
                continue
            path = os.path.join(root, name)
            rows = 0
            try:
                probe = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                rows = probe.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
                probe.close()
            except Exception:
                continue
            results.append((path, rows, os.path.getmtime(path)))
    results.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return results


def import_legacy_database(src_path):
    """把旧库的积分记录合并进当前库，返回 (总数, 实际导入数)。"""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in src.execute("PRAGMA table_info(scores)")}
        required = {"class_name", "title", "amount", "code", "hash", "issue_date"}
        if not required.issubset(columns):
            raise ValueError("该数据库不是本系统的数据表（缺少必要字段）")

        has_status = "status" in columns
        has_time = "verified_at" in columns
        rows = src.execute("SELECT * FROM scores").fetchall()
    finally:
        src.close()

    init_db()
    db = connect_db()
    try:
        with db:
            before = db.total_changes
            for row in rows:
                db.execute(
                    "INSERT OR IGNORE INTO scores"
                    " (class_name, title, amount, code, hash, issue_date, status, verified_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["class_name"], row["title"], row["amount"], row["code"], row["hash"],
                        row["issue_date"],
                        row["status"] if has_status else "未使用",
                        row["verified_at"] if has_time else None,
                    ),
                )
            inserted = db.total_changes - before
    finally:
        db.close()
    return len(rows), inserted


def human_size(size):
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# 打开数据库连接（统一 row_factory，避免硬编码下标）
def connect_db():
    conn = sqlite3.connect(get_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# 初始化数据库
def init_db():
    db_path = get_db_path()
    # 确保数据库目录存在
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 创建表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT NOT NULL,
        title TEXT NOT NULL,
        amount INTEGER NOT NULL,
        code TEXT UNIQUE NOT NULL,
        hash TEXT UNIQUE NOT NULL,
        issue_date TEXT NOT NULL,
        status TEXT DEFAULT '未使用',
        verified_at TEXT
    )''')
    # 兼容 v2/v3.0 老库：补核销时间列（可空、幂等，不动已有数据）
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(scores)")}
    if "verified_at" not in columns:
        cursor.execute("ALTER TABLE scores ADD COLUMN verified_at TEXT")
    conn.commit()
    conn.close()

# 生成积分码（8位短编号 + SHA-256哈希）
CODE_CHARS = string.ascii_uppercase + string.digits  # A-Z + 0-9

def generate_score_code(class_name, title, amount, salt=None):
    """返回 (短编号, 哈希值)。短编号10位用于条码和核销，哈希列保留以备后续签名校验。

    salt 由调用方一次读取后传入，避免批量生成时每张卡都读一次配置文件。
    """
    if salt is None:
        salt = read_config()["system"]["encryption_salt"]
    short_code = ''.join(secrets.choice(CODE_CHARS) for _ in range(10))
    # 用短编号 + 业务数据生成哈希做防伪
    timestamp = datetime.datetime.now().isoformat()
    data = f"{short_code}{class_name}{title}{amount}{timestamp}"
    hash_obj = hashlib.sha256((data + salt).encode())
    return short_code, hash_obj.hexdigest()

# 生成Code128条码图片到内存
def generate_barcode_image(barcode_data):
    """生成Code128条码PNG图片，返回BytesIO对象。barcode_data为条码内容（含面额的编码）"""
    Code128 = barcode.get_barcode_class('code128')
    code = Code128(barcode_data, writer=barcode.writer.ImageWriter())
    buf = io.BytesIO()
    code.write(buf, options={
        'module_width': 0.25,
        'module_height': 7.0,
        'write_text': False,
        'quiet_zone': 0.5,
        'format': 'PNG',
    })
    buf.seek(0)
    return buf

# 辅助：给段落添加 tab stop
def add_tab_stop(paragraph, tab_val, tab_pos):
    pPr = paragraph._element.get_or_add_pPr()
    tabs = pPr.makeelement(qn('w:tabs'), {})
    tab = tabs.makeelement(qn('w:tab'), {
        qn('w:val'): tab_val,
        qn('w:pos'): tab_pos,
    })
    tabs.append(tab)
    pPr.append(tabs)

# 辅助：生成面额文本框（锚定在段落右侧，三号字大字效果）
_shape_id_counter = [100]

def make_amount_textbox(amount_text):
    """生成面额文本框的 mc:AlternateContent XML 元素"""
    _shape_id_counter[0] += 1
    doc_pr_id = _shape_id_counter[0]
    font_sz = 32  # 三号 = 16pt = 半磅单位32
    cx = 706120   # 文本框宽
    cy = 325120   # 文本框高（约两行）
    pos_h = 1386840  # 水平偏移
    pos_v = 19050    # 垂直偏移

    xml_template = f'''<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <mc:Choice Requires="wps">
    <w:drawing>
      <wp:anchor distT="0" distB="0" distL="114300" distR="114300" simplePos="0"
        relativeHeight="251659264" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="column">
          <wp:posOffset>{pos_h}</wp:posOffset>
        </wp:positionH>
        <wp:positionV relativeFrom="paragraph">
          <wp:posOffset>{pos_v}</wp:posOffset>
        </wp:positionV>
        <wp:extent cx="{cx}" cy="{cy}"/>
        <wp:effectExtent l="0" t="0" r="10160" b="10160"/>
        <wp:wrapNone/>
        <wp:docPr id="{doc_pr_id}" name="文本框 {doc_pr_id}"/>
        <wp:cNvGraphicFramePr/>
        <a:graphic>
          <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
            <wps:wsp>
              <wps:cNvSpPr txBox="1"/>
              <wps:spPr>
                <a:xfrm>
                  <a:off x="0" y="0"/>
                  <a:ext cx="{cx}" cy="{cy}"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                <a:solidFill><a:schemeClr val="lt1"/></a:solidFill>
                <a:ln w="6350"><a:noFill/></a:ln>
              </wps:spPr>
              <wps:txbx>
                <w:txbxContent>
                  <w:p>
                    <w:pPr>
                      <w:rPr>
                        <w:sz w:val="{font_sz}"/>
                        <w:szCs w:val="{font_sz}"/>
                      </w:rPr>
                    </w:pPr>
                    <w:r>
                      <w:rPr>
                        <w:b/>
                        <w:sz w:val="{font_sz}"/>
                        <w:szCs w:val="{font_sz}"/>
                      </w:rPr>
                      <w:t>{amount_text}</w:t>
                    </w:r>
                  </w:p>
                </w:txbxContent>
              </wps:txbx>
              <wps:bodyPr rot="0" spcFirstLastPara="0" vertOverflow="overflow"
                horzOverflow="overflow" vert="horz" wrap="square"
                lIns="91440" tIns="45720" rIns="91440" bIns="45720"
                numCol="1" spcCol="0" rtlCol="0" fromWordArt="0"
                anchor="t" anchorCtr="0" forceAA="0" compatLnSpc="1">
                <a:noAutofit/>
              </wps:bodyPr>
            </wps:wsp>
          </a:graphicData>
        </a:graphic>
      </wp:anchor>
    </w:drawing>
  </mc:Choice>
</mc:AlternateContent>'''
    return etree.fromstring(xml_template.encode('utf-8'))

# 把用户输入变成安全的文件名片段（防路径穿越：去掉分隔符与保留字符）
def safe_path_part(text, max_len=60):
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(text))
    cleaned = cleaned.strip().strip(".").replace("..", "_")
    return cleaned[:max_len] or "未命名"

# 导出Word文档
def export_to_word(class_name, title, amount, codes, issue_date):
    config = read_config()
    output_dir = config["paths"]["output"]
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(BASE_DIR, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    doc = Document()

    # 设置页面边距
    for section in doc.sections:
        section.left_margin = Cm(1.0)
        section.right_margin = Cm(1.0)
        section.top_margin = Cm(0.5)
        section.bottom_margin = Cm(0.5)

    # 每页 CARD_ROWS_PER_PAGE 行 × CARD_COLUMNS_PER_PAGE 列
    rows_per_page = CARD_ROWS_PER_PAGE
    columns = CARD_COLUMNS_PER_PAGE
    column_width = CARD_COLUMN_WIDTH_CM  # cm
    row_height_twip = CARD_ROW_HEIGHT_TWIP  # ≈3.76cm，exact固定
    items_per_page = rows_per_page * columns
    tab_right_pos = str(int(column_width * 567))

    for page_idx, page_codes in enumerate([codes[i:i+items_per_page] for i in range(0, len(codes), items_per_page)]):
        if page_idx > 0:
            doc.add_page_break()

        # 始终使用完整的8行表格，避免浪费纸张
        table = doc.add_table(rows=rows_per_page, cols=columns)
        table.autofit = False
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # 设置列宽 + 固定行高 + 垂直居中
        for row in table.rows:
            tr = row._tr
            trPr = tr.get_or_add_trPr()
            trHeight = trPr.makeelement(qn('w:trHeight'), {
                qn('w:val'): row_height_twip,
                qn('w:hRule'): 'exact',
            })
            trPr.append(trHeight)

            for cell in row.cells:
                cell.width = Cm(column_width)
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                vAlign = tcPr.makeelement(qn('w:vAlign'), {qn('w:val'): 'center'})
                tcPr.append(vAlign)
                
                # 设置单元格边框为黑色
                tcBorders = tcPr.makeelement(qn('w:tcBorders'))
                
                # 上边框
                top = tcBorders.makeelement(qn('w:top'), {
                    qn('w:val'): 'single',
                    qn('w:sz'): '4',
                    qn('w:space'): '0',
                    qn('w:color'): '000000'
                })
                tcBorders.append(top)
                
                # 下边框
                bottom = tcBorders.makeelement(qn('w:bottom'), {
                    qn('w:val'): 'single',
                    qn('w:sz'): '4',
                    qn('w:space'): '0',
                    qn('w:color'): '000000'
                })
                tcBorders.append(bottom)
                
                # 左边框
                left = tcBorders.makeelement(qn('w:left'), {
                    qn('w:val'): 'single',
                    qn('w:sz'): '4',
                    qn('w:space'): '0',
                    qn('w:color'): '000000'
                })
                tcBorders.append(left)
                
                # 右边框
                right = tcBorders.makeelement(qn('w:right'), {
                    qn('w:val'): 'single',
                    qn('w:sz'): '4',
                    qn('w:space'): '0',
                    qn('w:color'): '000000'
                })
                tcBorders.append(right)
                
                tcPr.append(tcBorders)

        # 填充数据
        for i, code in enumerate(page_codes):
            row_idx = i // columns
            col_idx = i % columns
            cell = table.cell(row_idx, col_idx)

            # 清空默认段落
            for p in cell.paragraphs:
                p._element.getparent().remove(p._element)

            # 段落0：班级积分卡 + 右面板额文本框
            p = cell.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.first_line_indent = Pt(0)

            run_box = p.add_run()
            run_box._element.append(make_amount_textbox(f"{amount}分"))

            run = p.add_run("班级积分卡")
            run.bold = True
            run.font.size = Pt(10)

            # 段落1：班级（tab stop左靠）
            p = cell.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            add_tab_stop(p, 'right', tab_right_pos)
            run = p.add_run(f"班级：{class_name}")
            run.font.size = Pt(9)
            p.add_run('\t')

            # 段落2：标题 + 日期（tab stop左右锚定）
            p = cell.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(1)
            add_tab_stop(p, 'right', tab_right_pos)
            run = p.add_run(f"标题：{title}")
            run.font.size = Pt(9)
            p.add_run('\t')
            run = p.add_run(f"日期：{issue_date}")
            run.font.size = Pt(9)

            # 段落3：条码图片
            barcode_buf = generate_barcode_image(code)
            p = cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run()
            run.add_picture(barcode_buf, width=Cm(5))

            # 段落4：编号
            p = cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(code)
            run.font.size = Pt(8)
            run.font.name = 'Consolas'
        
        # 对于最后一页，填充剩余的空白单元格
        total_cells = rows_per_page * columns
        for i in range(len(page_codes), total_cells):
            row_idx = i // columns
            col_idx = i % columns
            cell = table.cell(row_idx, col_idx)
            # 清空默认段落
            for p in cell.paragraphs:
                p._element.getparent().remove(p._element)

    filename = (f"{safe_path_part(class_name)}_{safe_path_part(title)}_"
                f"{safe_path_part(amount, 12)}分_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.docx")
    filepath = os.path.join(output_dir, filename)
    doc.save(filepath)
    return filepath

# 检查是否已登录
def get_current_user(request: Request):
    _, sess = get_session(request)
    return sess["user"] if sess else None

# 安全防护中间件
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 防止访问敏感文件，静默跳转登录页（前缀/精确匹配，避免子串误伤正常路由）
    path = request.url.path
    if path.startswith(("/data/", "/db/")) or path in (
        "/config.json", "/Dockerfile", "/docker-compose.yml", "/requirements.txt"
    ):
        return RedirectResponse(url="/login")

    # CSRF 双提交令牌：token 同时放在 cookie 与表单隐藏域
    token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    request.state.csrf_token = token
    _prune_sessions()

    response = await call_next(request)
    if request.cookies.get(CSRF_COOKIE) != token:
        response.set_cookie(CSRF_COOKIE, token, samesite="lax", httponly=False)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response

# 初始化页的一次性提示（导入旧库结果等）
_init_notice = None


# 初始化管理员页面
@app.get("/", response_class=HTMLResponse)
async def init_admin(request: Request):
    global _init_notice
    config = read_config()
    if config["system"]["init_required"]:
        notice = _init_notice
        _init_notice = None
        return render(request, "init_admin.html", {
            "system_name": config["system"]["name"],
            "notice": notice,
        })
    return RedirectResponse(url="/login")

# 从 2.x 旧版本导入数据库（仅首次初始化时可用）
@app.post("/import_legacy")
def import_legacy(request: Request, legacy_path: str = Form(None),
                  csrf_token: str = Form(None)):
    global _init_notice
    check_csrf(request, csrf_token)

    config = read_config()
    init_mode = bool(config["system"].get("init_required"))
    sid, sess = get_session(request)

    # 初始化阶段无需登录；已初始化的系统必须登录后才能导入
    if not init_mode and not sess:
        raise HTTPException(status_code=403, detail="请先登录再导入旧数据")

    target = "/" if init_mode else "/setting"

    def finish(kind, text):
        if init_mode:
            return _finish_init_notice(kind, text)
        sess["notice"] = {"kind": kind, "text": text}
        return RedirectResponse(url=target, status_code=303)

    folder = (legacy_path or "").strip().strip('"')
    if not folder:
        picked = pick_folder("选择旧版程序安装目录")
        if picked is None:
            return finish("error", "打不开文件夹选择框，请在桌面版中使用该功能")
        if picked == "":
            # 用户点了取消：按原路返回，不做任何提示
            return RedirectResponse(url=target, status_code=303)
        folder = picked

    if not os.path.isdir(folder):
        return finish("error", f"路径不存在：{folder}")

    candidates = find_legacy_databases(folder)
    if not candidates:
        return finish("error", f"没有在该目录下找到 scores.db：{folder}")

    src_path, _, _ = candidates[0]
    try:
        total, inserted = import_legacy_database(src_path)
    except Exception as exc:
        return finish("error", f"导入失败：{exc}")

    skipped = total - inserted
    text = f"已从 {src_path} 导入 {inserted} 条记录"
    if skipped > 0:
        text += f"（跳过重复 {skipped} 条）"
    return finish("success", text)


def _finish_init_notice(kind, text):
    global _init_notice
    _init_notice = {"kind": kind, "text": text}
    return RedirectResponse(url="/", status_code=303)


# 提交管理员初始化
@app.post("/init_admin")
async def submit_init_admin(request: Request, username: str = Form(...), password: str = Form(...),
                            csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    config = read_config()
    # 只在尚未初始化时允许设置管理员，防止匿名用户覆盖已有账号
    if not config["system"].get("init_required"):
        raise HTTPException(status_code=403, detail="系统已初始化，请直接登录")

    username = (username or "").strip()
    system_name = config["system"]["name"]
    if not 1 <= len(username) <= 32:
        return render(request, "init_admin.html", {"system_name": system_name, "error": "用户名长度需为 1-32 个字符"})
    if len(password or "") < 4:
        return render(request, "init_admin.html", {"system_name": system_name, "error": "密码至少 4 位"})

    config["admin"]["username"] = username
    config["admin"]["password"] = hash_password(password)
    config["system"]["init_required"] = False
    write_config(config)

    # 初始化完成直接建立会话进入控制台，不再要求重新登录一次
    session_id = secrets.token_hex(32)
    sessions[session_id] = {"user": username, "expires": time.time() + SESSION_TTL}
    response = RedirectResponse(url="/index", status_code=303)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax",
                        secure=_is_https(request), max_age=SESSION_TTL)
    return response

# 登录页面
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    config = read_config()
    if config["system"]["init_required"]:
        return RedirectResponse(url="/")
    return render(request, "login.html", {"system_name": config["system"]["name"], "error": False})

# 提交登录
@app.post("/login")
async def submit_login(request: Request, username: str = Form(...), password: str = Form(...),
                       csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    config = read_config()
    system_name = config["system"]["name"]
    ip = _client_ip(request)

    wait = _login_wait_seconds(ip)
    if wait:
        return render(request, "login.html", {
            "system_name": system_name, "error": True,
            "message": f"登录失败次数过多，请 {wait} 秒后再试",
        })

    ok, needs_upgrade = verify_password(password or "", config["admin"]["password"])
    if config["admin"]["username"] != username or not ok:
        _note_login_failure(ip)
        return render(request, "login.html", {"system_name": system_name, "error": True})

    _clear_login_failures(ip)
    # 历史明文口令登录成功后自动升级为 PBKDF2 哈希
    if needs_upgrade:
        config["admin"]["password"] = hash_password(password)
        write_config(config)

    session_id = secrets.token_hex(32)
    sessions[session_id] = {"user": username, "expires": time.time() + SESSION_TTL}
    response = RedirectResponse(url="/index", status_code=303)
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite="lax",
                        secure=_is_https(request), max_age=SESSION_TTL)
    return response

# 登出
@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        sessions.pop(session_id, None)
    response = RedirectResponse(url="/login")
    response.delete_cookie(SESSION_COOKIE)
    return response

# 首页
@app.get("/index", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    config = read_config()
    system_name = config["system"]["name"]
    return render(request, "index.html", {"system_name": system_name})

# 生成积分页面
@app.get("/generate", response_class=HTMLResponse)
async def generate(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    config = read_config()
    system_name = config["system"]["name"]
    return render(request, "generate.html", {"system_name": system_name, "success": False})

# 提交生成积分（结果存会话，避免多人共用时互相串号）
@app.post("/generate")
async def submit_generate(request: Request, class_name: str = Form(...), title: str = Form(...),
                          amount: int = Form(...), quantity: int = Form(...),
                          csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    config = read_config()
    system_name = config["system"]["name"]
    salt = config["system"]["encryption_salt"]

    class_name = (class_name or "").strip()
    title = (title or "").strip()
    if not class_name or not title:
        return render(request, "generate.html", {
            "system_name": system_name, "success": False, "error": "班级名称和积分卡标题都不能为空"})
    if amount <= 0:
        return render(request, "generate.html", {
            "system_name": system_name, "success": False, "error": "单张面额必须大于 0"})
    if not 1 <= quantity <= MAX_QUANTITY:
        return render(request, "generate.html", {
            "system_name": system_name, "success": False,
            "error": f"单次生成数量需在 1-{MAX_QUANTITY} 之间"})

    init_db()
    issue_date = datetime.datetime.now().strftime("%Y-%m-%d")
    codes = []

    conn = connect_db()
    try:
        with conn:
            for _ in range(quantity):
                # 短码撞车概率极低，但一旦撞车就重生成，保证 Word 上每张卡都能核销
                while True:
                    short_code, hash_val = generate_score_code(class_name, title, amount, salt)
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO scores (class_name, title, amount, code, hash, issue_date, status)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (class_name, title, amount, short_code, hash_val, issue_date, "未使用")
                    )
                    if cur.rowcount == 1:
                        codes.append(short_code)
                        break
    finally:
        conn.close()

    # 导出Word
    filepath = export_to_word(class_name, title, amount, codes, issue_date)

    sess["gen"] = {
        "system_name": system_name,
        "filepath": filepath,
        "filename": os.path.basename(filepath),
        "quantity": quantity,
    }
    return RedirectResponse(url="/generate_result", status_code=303)

# 生成结果页（防止刷新重复提交）
@app.get("/generate_result", response_class=HTMLResponse)
async def generate_result(request: Request):
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login")
    result = sess.get("gen")
    if not result:
        return RedirectResponse(url="/generate")
    notice = sess.pop("gen_notice", None)
    return render(request, "generate.html", {
        "system_name": result["system_name"],
        "success": True,
        "filepath": result["filepath"],
        "filename": result["filename"],
        "quantity": result["quantity"],
        "notice": notice,
    })

# 核销页面
@app.get("/verify", response_class=HTMLResponse)
async def verify(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    config = read_config()
    system_name = config["system"]["name"]
    return render(request, "verify.html", {"system_name": system_name, "results": None,
                                           "total_amount": 0, "error": None})

# 提交核销
@app.post("/verify")
async def submit_verify(request: Request, codes: str = Form(None), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    config = read_config()
    system_name = config["system"]["name"]

    # 空编码检查
    if not codes or not codes.strip():
        return render(request, "verify.html", {
            "system_name": system_name,
            "results": None,
            "total_amount": 0,
            "error": "请输入或扫描积分编号后再核销",
        })

    init_db()
    code_list = [code.strip().upper() for code in codes.split() if code.strip()]
    # 单次核销条数上限，避免一次提交把数据库/线程占满
    if len(code_list) > MAX_QUANTITY:
        return render(request, "verify.html", {
            "system_name": system_name, "results": None, "total_amount": 0,
            "error": f"单次核销数量不能超过 {MAX_QUANTITY} 条",
        })

    results = []
    total_amount = 0
    verified_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect_db()
    try:
        for i, code in enumerate(code_list, 1):
            score = conn.execute(
                "SELECT * FROM scores WHERE code = ? OR hash = ?", (code, code)
            ).fetchone()

            if not score:
                results.append({"index": i, "code": code, "amount": 0,
                                "status": "错误", "message": "伪造编码",
                                "verified_at": None, "time_text": ""})
                continue

            # 条件更新 + rowcount 判定：并发/重复提交时只有一次能成功，杜绝一卡多花
            cur = conn.execute(
                "UPDATE scores SET status = '已作废', verified_at = ?"
                " WHERE code = ? AND status = '未使用'",
                (verified_now, score["code"])
            )
            if cur.rowcount == 1:
                results.append({"index": i, "code": code, "amount": score["amount"],
                                "status": "成功", "message": "核销成功",
                                "verified_at": verified_now, "time_text": verified_now})
                total_amount += score["amount"]
            else:
                # 已核销的卡：回显当初的核销时间（早于该字段的老数据标记为「未记录」）
                redeemed_at = score["verified_at"]
                results.append({"index": i, "code": code, "amount": score["amount"],
                                "status": "错误", "message": "已核销编码",
                                "verified_at": redeemed_at,
                                "time_text": redeemed_at or "未记录"})
        conn.commit()
    finally:
        conn.close()

    sess["verify"] = {
        "system_name": system_name,
        "results": results,
        "total_amount": total_amount,
    }
    return RedirectResponse(url="/verify_result", status_code=303)

# 核销结果页（防止刷新重复提交）
@app.get("/verify_result", response_class=HTMLResponse)
async def verify_result(request: Request):
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login")
    result = sess.pop("verify", None)
    if not result:
        return RedirectResponse(url="/verify")
    results = result["results"]
    ok_count = sum(1 for r in results if r.get("status") == "成功")
    return render(request, "verify.html", {
        "system_name": result["system_name"],
        "results": results,
        "ok_count": ok_count,
        "fail_count": len(results) - ok_count,
        "total_amount": result["total_amount"],
        "error": None,
    })

# 设置页面（GET，读取本会话上次结果）
@app.get("/setting", response_class=HTMLResponse)
async def setting(request: Request):
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login")
    config = read_config()
    system_name = config["system"]["name"]
    result = sess.pop("setting", None)
    notice = sess.pop("notice", None)

    backup_cfg = config.get("backup", {}) or {}
    try:
        interval_value = int(round(float(backup_cfg.get("interval_hours", 24) or 0)))
    except (TypeError, ValueError):
        interval_value = 24
    printers, default_printer = list_printers()
    print_cfg = config.get("print", {}) or {}
    out_count, out_size = output_stats()
    junk_count, junk_size = junk_stats()

    return render(request, "setting.html", {
        "system_name": system_name,
        "success": result == "success",
        "wrong_password": result == "wrong_password",
        "reset_wrong_password": result == "reset_wrong_password",
        "message": "新密码至少需要 4 位" if result == "weak" else None,
        "notice": notice,
        "backup_count": len(list_backups()),
        "last_backup": last_backup_time(),
        "backup_dir": get_backup_dir(),
        "interval_hours": interval_value,
        "backup_keep": backup_cfg.get("keep", 10),
        "autostart": bool((config.get("desktop") or {}).get("autostart", False)),
        "printers": printers,
        "default_printer": default_printer,
        "printer_value": print_cfg.get("printer", "") or "",
        "cache_count": out_count,
        "cache_size": human_size(out_size),
        "junk_count": junk_count,
        "junk_size": human_size(junk_size),
    })

# 提交修改密码
@app.post("/setting")
async def submit_setting(request: Request, current_password: str = Form(...), password: str = Form(...),
                         csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    config = read_config()
    ok, _ = verify_password(current_password or "", config["admin"]["password"])
    if not ok:
        sess["setting"] = "wrong_password"
        return RedirectResponse(url="/setting", status_code=303)
    if len(password or "") < 4:
        sess["setting"] = "weak"
        return RedirectResponse(url="/setting", status_code=303)
    config["admin"]["password"] = hash_password(password)
    write_config(config)
    sess["setting"] = "success"
    return RedirectResponse(url="/setting", status_code=303)

# 恢复出厂设置
def do_reset():
    """删除数据库、清空配置、删除输出文件"""
    # 删除数据库
    db_path = get_db_path()
    if os.path.exists(db_path):
        os.remove(db_path)
    # 删除output目录中的文件
    config = read_config()
    output_dir = config["paths"]["output"]
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(BASE_DIR, output_dir)
    if os.path.isdir(output_dir):
        for f in os.listdir(output_dir):
            fp = os.path.join(output_dir, f)
            if os.path.isfile(fp):
                try:
                    os.remove(fp)
                except PermissionError:
                    pass  # 文件被占用，跳过
    # 重置配置（使用默认配置，init_required=True）
    write_config(get_default_config())
    # 清空会话与登录节流记录
    sessions.clear()
    _login_failures.clear()

# ---------------- 备份 ----------------

@app.post("/backup/now")
async def backup_now(request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    try:
        name = create_backup()
        sess["notice"] = {"kind": "success", "text": f"已创建备份：{name}"}
    except Exception as exc:
        sess["notice"] = {"kind": "error", "text": f"备份失败：{exc}"}
    return RedirectResponse(url="/setting", status_code=303)


@app.post("/backup/open")
async def backup_open(request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    directory = get_backup_dir()
    opened = False
    if os.name == "nt":
        try:
            os.startfile(directory)      # 本机运行时直接在资源管理器打开
            opened = True
        except Exception:
            opened = False

    sess["notice"] = {
        "kind": "success" if opened else "info",
        "text": f"备份目录：{directory}" if opened else f"请在文件管理器中打开：{directory}",
    }
    return RedirectResponse(url="/setting", status_code=303)


@app.post("/backup/settings")
async def backup_settings(request: Request, interval_hours: int = Form(24),
                          keep: int = Form(10), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    if interval_hours < 0 or interval_hours > MAX_BACKUP_HOURS:
        sess["notice"] = {"kind": "error", "text": f"备份间隔需在 0 - {MAX_BACKUP_HOURS} 小时之间（0 表示关闭定时备份）"}
        return RedirectResponse(url="/setting", status_code=303)
    if not 1 <= keep <= MAX_BACKUP_KEEP:
        sess["notice"] = {"kind": "error", "text": f"保留份数需在 1 - {MAX_BACKUP_KEEP} 之间"}
        return RedirectResponse(url="/setting", status_code=303)

    config = read_config()
    config.setdefault("backup", {})
    config["backup"]["interval_hours"] = interval_hours
    config["backup"]["keep"] = keep
    write_config(config)

    sess["notice"] = {"kind": "success", "text": "备份设置已保存"}
    return RedirectResponse(url="/setting", status_code=303)


@app.post("/print/settings")
async def print_settings(request: Request, printer: str = Form(""), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    printer = (printer or "").strip()
    if printer:
        names, _ = list_printers()
        if printer not in names:
            sess["notice"] = {"kind": "error", "text": f"找不到该打印机：{printer}"}
            return RedirectResponse(url="/setting", status_code=303)

    config = read_config()
    config.setdefault("print", {})
    config["print"]["printer"] = printer
    write_config(config)

    sess["notice"] = {
        "kind": "success",
        "text": f"打印将使用：{printer}" if printer else "打印将使用系统默认打印机",
    }
    return RedirectResponse(url="/setting", status_code=303)


@app.post("/desktop/autostart")
async def desktop_autostart(request: Request, autostart: str = Form(None),
                            csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    enabled = bool(autostart)
    config = read_config()
    config.setdefault("desktop", {})
    config["desktop"]["autostart"] = enabled
    write_config(config)

    sess["notice"] = {
        "kind": "success",
        "text": "已开启开机自启，下次启动桌面版时生效" if enabled else "已关闭开机自启",
    }
    return RedirectResponse(url="/setting", status_code=303)


# ---------------- 清理 ----------------

@app.post("/cleanup/cache")
async def cleanup_cache(request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    removed, freed = clean_output()
    sess["notice"] = {"kind": "success", "text": f"已清理 {removed} 个导出文件，释放 {human_size(freed)}"}
    return RedirectResponse(url="/setting", status_code=303)


@app.post("/cleanup/junk")
async def cleanup_junk(request: Request, csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    removed, freed = clean_junk()
    sess["notice"] = {"kind": "success", "text": f"已清理 {removed} 项垃圾文件，释放 {human_size(freed)}"}
    return RedirectResponse(url="/setting", status_code=303)


# 提交恢复出厂设置
@app.post("/reset")
async def reset_system(request: Request, reset_password: str = Form(...), csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)
    config = read_config()
    ok, _ = verify_password(reset_password or "", config["admin"]["password"])
    if not ok:
        sess["setting"] = "reset_wrong_password"
        return RedirectResponse(url="/setting", status_code=303)
    do_reset()
    return RedirectResponse(url="/", status_code=303)


# 直接调用系统打印（默认打印机），交给关联程序（Word / WPS）处理
@app.post("/print")
async def print_document(request: Request, filename: str = Form(...),
                         csrf_token: str = Form(None)):
    check_csrf(request, csrf_token)
    sid, sess = get_session(request)
    if not sess:
        return RedirectResponse(url="/login", status_code=303)

    target = "/generate_result" if sess.get("gen") else "/generate"

    name = os.path.basename(filename.replace("\\", "/"))
    output_dir = get_output_dir()
    filepath = os.path.realpath(os.path.join(output_dir, name))
    try:
        inside = os.path.commonpath([filepath, output_dir]) == output_dir
    except ValueError:
        inside = False

    if not name or not name.lower().endswith(".docx") or not inside or not os.path.isfile(filepath):
        sess["gen_notice"] = {"kind": "error", "text": "找不到要打印的文件"}
        return RedirectResponse(url=target, status_code=303)

    printer = (read_config().get("print", {}) or {}).get("printer", "") or ""
    try:
        used = send_to_printer(filepath, printer)
        sess["gen_notice"] = {"kind": "success", "text": f"已发送到打印机：{used}"}
    except Exception as exc:
        sess["gen_notice"] = {"kind": "error", "text": f"无法调用打印机：{exc}"}

    return RedirectResponse(url=target, status_code=303)


# 导出目录绝对路径
def get_output_dir():
    output_dir = read_config()["paths"]["output"]
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(BASE_DIR, output_dir)
    return os.path.realpath(output_dir)


# 下载生成的Word文件
@app.get("/download/{filename}")
async def download_file(request: Request, filename: str):
    if not get_current_user(request):
        return RedirectResponse(url="/login")

    # 只允许下载导出目录内的 .docx，挡掉 ..\ / ../ 之类穿越（Windows 反斜杠同样算分隔符）
    name = os.path.basename(filename.replace("\\", "/"))
    if not name or name != filename or not name.lower().endswith(".docx"):
        raise HTTPException(status_code=404, detail="文件不存在")

    output_dir = get_output_dir()
    filepath = os.path.realpath(os.path.join(output_dir, name))
    try:
        inside = os.path.commonpath([filepath, output_dir]) == output_dir
    except ValueError:          # 跨盘符
        inside = False
    if not inside or not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        filepath,
        filename=name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# 初始化数据库
init_db()

# 启动定时备份（按 data/config.json 里的 backup.interval_hours）
start_backup_scheduler()
