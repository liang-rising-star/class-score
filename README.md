<div align="center">

# 🎫 班级积分管理系统

**轻量 · 安全 · 开箱即用** 的积分卡生成与核销平台

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.en.html)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Docker Hub](https://img.shields.io/badge/Docker%20Hub-Repository-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/wsxxstar/class-score)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-181717?logo=github&logoColor=white)](https://github.com/liang-rising-star/class-score)

</div>

---
>  **了解使用方式，请跳过此处，往下翻**

## 📋 项目简介

班级积分管理系统是一款专为教育场景设计的积分卡管理工具，旨在解决传统积分卡容易伪造、难以管理的问题。

### 核心功能

- 🔐 **双重防伪** — 每张积分卡配备 10 位唯一编号 + SHA-256 哈希校验，伪造几乎不可能
- 📦 **批量生成** — 一键批量生成积分卡，自动导出排版精美的 A4 Word 文档
- 🔍 **快速核销** — 扫码枪扫入或手动输入编号核销，一次提交多个编码
- 🏷️ **Code128 条码** — 兼容所有标准条码扫描枪，即扫即核
- 🌐 **局域网可用** — 纯 HTTP 即可使用，无线网络下的手机、平板都能录入核销
- 🛡️ **盐值轮转** — 恢复出厂设置时自动重新生成加密盐，使所有旧卡失效
- 🚀 **零外部依赖** — 内置 SQLite 数据库，无需额外安装数据库服务
- 🐳 **Docker 一键部署** — 一行命令启动，数据自动持久化
- 🎨 **简洁中文界面** — 全中文响应式 UI，专注教育场景

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

#### Docker 镜像版本

| 版本标签 | 架构 | 说明 |
|:---:|:---:|:---|
| `latest` | x86 | 最新版本 |
| `2.0` | x86 | 稳定版本 2.0 |
| `1.0` | x86 | 稳定版本 1.0 |
| - | ARM | 暂未构建（后续有计划） |

> 💡 **ARM 架构说明**：目前暂未构建 ARM 架构的镜像，后续有计划支持。如果需要在 ARM 设备上运行，请自行拉取代码构建。

#### 使用 Docker run

```bash
docker run -d --name class-score -p 8000:8000 -v ./data:/app/data wsxxstar/class-score:latest
```

#### 使用 Docker Compose

```yaml
services:
  class-score:
    image: wsxxstar/class-score:latest
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### 方式二：本地运行
#### 使用本机Python运行服务
```bash
cd class-score-system

# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py
```

Windows 用户可直接双击 `启动.bat` 或 `run.exe`（内置 Python 运行时，无需安装 Python）。

### 方式三：桌面应用（WebView2，托盘常驻）

`desktop/` 是一个 C# WinForms 外壳，用 **WebView2** 内嵌网页，并自动拉起内嵌 Python 后端（固定端口 **3445**）。

```bash
# 需要 .NET SDK 8+ 与 WebView2 运行时（Win10/11 通常已自带）
cd desktop
dotnet build -c Release

# 推荐用启动器运行：会把产物复制到 %LOCALAPPDATA%\ClassScore-Desktoppp 再启动
启动桌面版.bat
# 也可直接跑产物：desktop/bin/Release/net8.0-windows/ClassScore.Desktop.exe
```

> 💡 为什么推荐启动器：直接在工作区/只读位置运行 exe 时，进程可能继承受限的完整性级别，
> WebView2 会因无法写入下载目录而提示“没有权限，请保存到文档文件夹”。
> 复制到 `%LOCALAPPDATA%` 后进程拥有正常权限。若坚持原地运行，可用管理员命令行修正：
> `icacls "desktopin" /setintegritylevel (OI)(CI)Medium /T`

用法：

- 双击 exe 直接进主界面，后端由它自己启动/停止，不用再开命令行窗口
- **单实例**：程序已在后台运行时再次双击 exe，不会开第二个进程，而是把已有窗口叫到前台
- 支持 `--tray` 参数：启动后只驻留托盘不弹窗（设置里的「开机自启」就是用这个参数登记的）
- 点窗口右上角 **×** 只是收进**系统托盘**，后台继续运行
- 托盘图标：**双击**打开主界面，**右键**菜单 → 打开主界面 / **重启系统** / **退出**
  - 「重启系统」是整体重启：托盘图标和窗口先消失，随后自动启动新进程（后端也一起重启），
    适合改了配置或代码后重新加载；重启后需要重新登录
- 程序会从自身目录向上查找 `class-score-system\python\python.exe` 来定位项目根目录；
  也可以显式指定：`ClassScore.Desktop.exe --root "D:\class-score"`，或设环境变量 `CLASS_SCORE_ROOT`
- 导出文件走系统「另存为」对话框，自己选保存位置
- 运行时日志：`%LOCALAPPDATA%\ClassScore-Desktop\desktop.log`（后端启动失败时会写明原因）

> ⚠️ 桌面端只监听 `127.0.0.1:3445`，不对外网开放；需要局域网访问请用「方式二」的 Web 模式。
> 若双击后提示"后端服务未能启动"，多半是 exe 所在目录不可写（例如被安全软件或沙箱限制了写入），
> 把整个程序目录放到普通路径（如 `D:\class-score`）或以管理员身份运行即可。


> ⚠️ **关于内置 Python 运行时**：`class-score-system/python/`（约 430MB）不纳入版本管理。
> 从仓库克隆后，需要把 [Python 3.14 Windows embeddable 包](https://www.python.org/downloads/windows/)
> 解压到 `class-score-system/python/`，再用 [get-pip.py](https://bootstrap.pypa.io/get-pip.py) 装好 pip
> 并执行 `python\python.exe -m pip install -r requirements.txt`；或者干脆用本机 Python 运行（见上一节）。
> 用 PyInstaller / Inno Setup 打便携包时，这个目录必须存在。

#### 使用软件包内置 Python 运行时

如果使用内置 Python 运行时，可通过以下指令自定义端口：

```bash
# 切换到 class-score-system 目录
cd class-score-system

# 使用内置 Python 运行时并指定端口（例如 8080）
./python/python.exe run.py --port 8080
```

#### 修改运行.bat

要修改 `启动.bat` 文件以使用自定义端口，可按照以下步骤操作：

1. 用文本编辑器打开 `启动.bat` 文件
2. 修改其中的端口参数，例如：
   ```batch
   @echo off
   cd class-score-system
   .\python\python.exe run.py --port 8080
   pause
   ```
3. 保存文件后双击运行，服务将在指定端口启动

## ⚠️ 注意事项

### 服务启动
- 启动后会弹出命令行窗口，**请勿关闭**，关闭后服务将停止运行
- 服务默认运行在 `8000` 端口，请确保该端口未被占用（已被占用？请参考前文自定义端口方法）

### 访问方式
- 在本机浏览器中访问：`http://localhost:8000` 或 `http://127.0.0.1:8000`
- 在局域网其他设备上访问：`http://[此电脑的IP地址]:8000`
- 首次访问将引导设置管理员账号

### 数据持久化

所有数据都存储在 `data/` 目录中：

```
data/
├── config.json      # 系统配置
├── db/
│   └── scores.db    # SQLite 数据库
└── output/          # 导出的 Word 文档
```

> 💡 **配置文件丢失**：不用担心，系统会自动重建默认配置并重新引导管理员设置
> 💡 **数据备份**：建议定期备份 `data/` 目录，以防止数据丢失

## 🖼️ 界面预览

| 生成积分卡 | 核销积分卡 |
|:---:|:---:|
| 填写班级、标题、面额、数量 → 一键生成并保存 Word | 输入/扫描条码 → 实时显示核销结果与总额 |
| 3 列 × 7 行 排版，每张卡含条码 + 编号 | ✅ 核销成功 / ❌ 伪造编码 / ❌ 已核销 |

## 📖 使用说明

### 1️⃣ 初始化

首次访问系统时，需设置管理员用户名和密码。

如果是从 2.x 旧版本升级，可以先点「选择旧版安装目录并导入」：选中旧版程序的安装目录后，
系统会自动搜索其中的 `scores.db` 并导入全部积分记录（含已核销状态），导入完成后再创建管理员。
重复导入不会产生重复数据（已存在的编号会自动跳过）。

### 2️⃣ 生成积分卡

1. 登录后点击「生成积分」
2. 填写班级名称、积分卡标题、单张面额、生成数量
3. 点击生成 → 弹出另存为，选择保存位置
4. 打印文档，裁剪分发

### 3️⃣ 核销积分卡

1. 点击「核销积分」
2. 输入积分卡编号（一行一个，或空格分隔）
3. 也可使用条码扫描枪直接扫描
4. 查看核销结果与总额统计

### 4️⃣ 系统设置

- **修改密码** — 在设置页面输入当前密码与新密码
- **数据备份** — 一键把 `config.json` + `scores.db` 打包成 zip 存到 `data/backups`；
  「立即备份」立刻生成一份，「打开备份文件夹」直接跳转到该目录
- **定时备份** — 设置间隔（小时）与保留份数，后台每分钟检查一次，到期自动备份并删除最旧的；
  间隔填 `0` 关闭定时备份
- **桌面应用 → 开机自启** — 独立卡片，开关式滑块；开启后下次启动桌面版会把本程序登记到当前用户的
  启动项（带 `--tray` 参数，开机后只在托盘运行，双击图标才打开主界面）
- **清理** — 「已生成的导出文件」删除 `data/output` 里的 Word；「垃圾文件」删除 `__pycache__`、`*.pyc`、`*.tmp`；
  两类操作都会先弹窗显示数量与体积，确认后才执行
- **恢复出厂** — 弹窗内输入当前密码，清空所有数据并重置加密盐（⚠️ 旧积分卡将全部失效）

## 🛠️ 技术栈

| 层级 | 技术 |
|:---:|:---:|
| 后端 | FastAPI + Uvicorn |
| 数据库 | SQLite 3（内嵌） |
| 模板引擎 | Jinja2 |
| 条码生成 | python-barcode (Code128) + Pillow |
| 文档导出 | python-docx |
| 容器化 | Docker + Docker Compose |

## 📁 项目结构

```
class-score-system/       # Web 后端与前端模板
├── main.py              # 核心应用（FastAPI 路由 + 业务逻辑）
├── run.py               # 启动入口（支持 --reset 参数）
├── reset.py             # 恢复出厂设置脚本
├── generate_manual.py   # 用户手册生成器
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 镜像定义
├── docker-compose.yml   # Docker Compose 编排
├── entrypoint.sh        # 容器入口脚本
├── .dockerignore        # Docker 构建排除
├── templates/           # Jinja2 HTML 模板
│   ├── _sidebar.html    # 公共左侧菜单（五个内页共用）
│   ├── init_admin.html  # 管理员初始化页
│   ├── login.html       # 登录页
│   ├── index.html       # 控制台（首页）
│   ├── generate.html    # 生成积分页
│   ├── verify.html      # 核销积分页
│   └── setting.html     # 设置页
├── static/              # 静态资源
│   └── css/app.css      # 统一设计系统（颜色/圆角/阴影变量 + 组件样式）
desktop/                  # 桌面外壳（C# WinForms + WebView2，托盘常驻）
├── ClassScore.Desktop.csproj
└── Program.cs            # 后端拉起 / WebView2 窗口 / 托盘菜单
├── python/              # 内嵌 Python 运行时（不入库，见「方式二」说明）
└── data/                # 运行时数据（自动生成）
    ├── config.json
    ├── db/scores.db
    ├── backups/         # 定时/手动备份的 zip
    └── output/
```

## 🔒 安全设计

| 机制 | 说明 |
|:---|:---|
| 双重编码 | 10 位短编号（条码/人工录入）+ SHA-256 哈希（保留列，供后续签名校验）|
| 安装盐 | 每个实例独立加密盐，重置后旧卡全部失效 |
| 口令存储 | PBKDF2-SHA256（20 万轮加盐），旧版明文口令登录时自动升级 |
| 会话管理 | 64 字符随机 Session ID + HTTP-only Cookie，空闲 8 小时过期 |
| CSRF | 双提交令牌，所有 POST 表单校验，缺失即 403 |
| 登录节流 | 同一 IP 连续 5 次失败锁定 5 分钟 |
| 核销防双花 | 条件更新（`WHERE status='未使用'`）+ rowcount 判定，同一张卡只能核销一次 |
| 文件保护 | 中间件拦截敏感路径；下载仅限导出目录内的 `.docx`，拒绝路径穿越 |

## 🗃️ 数据库结构

```sql
CREATE TABLE scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name  TEXT    NOT NULL,          -- 班级名称
    title       TEXT    NOT NULL,          -- 积分卡标题
    amount      INTEGER NOT NULL,          -- 面额（分）
    code        TEXT    UNIQUE NOT NULL,   -- 10 位防伪编号
    hash        TEXT    UNIQUE NOT NULL,   -- SHA-256 防伪哈希
    issue_date  TEXT    NOT NULL,          -- 发放日期
    status      TEXT    DEFAULT '未使用',  -- 未使用 / 已作废
    verified_at TEXT                       -- 核销时间（成功核销时写入）
);
```

> 老库（无 `verified_at` 列）启动时自动 `ALTER TABLE` 补列，已有数据不受影响。

## ⚙️ 配置文件

`data/config.json`：

```json
{
  "system": {
    "name": "班级积分管理系统",
    "init_required": true,
    "encryption_salt": "<自动生成的32位hex>"
  },
  "paths": {
    "database": "./data/db/scores.db",
    "output": "./data/output"
  },
  "admin": {
    "username": "",
    "password": "<PBKDF2 哈希；旧版明文会在首次登录后自动升级>"
  }
}
```

> 打印版式（列数/行数/行高）是 `main.py` 顶部的 `CARD_*` 常量，不再放在配置里 ——
> 旧的 `printing` 段已废弃，保留也不会生效。

## 📄 开源协议

本项目基于 [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html) 开源。

---

<div align="center">

**Made with ❤️ for Education**

</div>
