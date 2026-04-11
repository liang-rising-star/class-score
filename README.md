<div align="center">

# 🎫 班级积分防伪核销管理系统

**轻量 · 安全 · 开箱即用** 的积分卡生成与核销平台

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.en.html)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

</div>

---

## 📋 项目简介

班级积分防伪核销管理系统是一款专为教育场景设计的积分卡管理工具，旨在解决传统积分卡容易伪造、难以管理的问题。

### 核心功能

- 🔐 **双重防伪** — 每张积分卡配备 10 位唯一编号 + SHA-256 哈希校验，伪造几乎不可能
- 📦 **批量生成** — 一键批量生成积分卡，自动导出排版精美的 A4 Word 文档
- 🔍 **快速核销** — 支持扫描条码或手动输入编号核销，一次提交多个编码
- 🏷️ **Code128 条码** — 兼容所有标准条码扫描枪，即扫即核
- 🛡️ **盐值轮转** — 恢复出厂设置时自动重新生成加密盐，使所有旧卡失效
- 🚀 **零外部依赖** — 内置 SQLite 数据库，无需额外安装数据库服务
- 🐳 **Docker 一键部署** — 一行命令启动，数据自动持久化
- 🎨 **简洁中文界面** — 全中文响应式 UI，专注教育场景

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

#### 使用 Docker run

```bash
# 直接运行预构建镜像
docker run -d --name class-score -p 8000:8000 -v ./data:/app/data wsxxstar/class-score
```

#### 使用 Docker Compose

```yaml
rvices:
  class-score:
    image: wsxxstar/class-score
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### 方式二：本地运行

```bash
cd class-score-system

# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py
```

Windows 用户可直接双击 `启动.bat`（内置 Python 运行时，无需安装 Python）。

### 访问系统

访问 `http://localhost:8000`，首次使用将引导设置管理员账号。

**数据持久化：**

```
data/
├── config.json      # 系统配置
├── db/
│   └── scores.db    # SQLite 数据库
└── output/          # 导出的 Word 文档
```

> 💡 配置文件丢失？不用担心，系统会自动重建默认配置并重新引导管理员设置。

## 🖼️ 界面预览

| 生成积分卡 | 核销积分卡 |
|:---:|:---:|
| 填写班级、标题、面额、数量 → 一键生成并下载 Word | 输入/扫描条码 → 实时显示核销结果与总额 |
| 2 列 × 5 行 排版，每张卡含条码 + 编号 | ✅ 核销成功 / ❌ 伪造编码 / ❌ 已核销 |

## 📖 使用说明

### 1️⃣ 初始化

首次访问系统时，需设置管理员用户名和密码。

### 2️⃣ 生成积分卡

1. 登录后点击「生成积分」
2. 填写班级名称、积分卡标题、单张面额、生成数量
3. 点击生成 → 自动下载 Word 文档
4. 打印文档，裁剪分发

### 3️⃣ 核销积分卡

1. 点击「核销积分」
2. 输入积分卡编号（一行一个，或空格分隔）
3. 也可使用条码扫描枪直接扫描
4. 查看核销结果与总额统计

### 4️⃣ 系统设置

- **修改密码** — 在设置页面输入当前密码与新密码
- **恢复出厂** — 需确认当前密码，将清空所有数据并重置加密盐（⚠️ 旧积分卡将全部失效）

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
class-score-system/
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
│   ├── init_admin.html  # 管理员初始化页
│   ├── login.html       # 登录页
│   ├── index.html       # 首页
│   ├── generate.html    # 生成积分页
│   ├── verify.html      # 核销积分页
│   └── setting.html     # 设置页
├── static/              # 静态资源
└── data/                # 运行时数据（自动生成）
    ├── config.json
    ├── db/scores.db
    └── output/
```

## 🔒 安全设计

| 机制 | 说明 |
|:---|:---|
| 双重编码 | 10 位短编号（条码/人工录入）+ SHA-256 哈希（防伪校验）|
| 安装盐 | 每个实例独立加密盐，重置后旧卡全部失效 |
| 会话管理 | 64 字符随机 Session ID + HTTP-only Cookie |
| 文件保护 | 中间件拦截敏感路径（`/config.json`、`/data/` 等）|
| 表单防重 | POST-Redirect-GET 模式，杜绝刷新重复提交 |

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
    status      TEXT    DEFAULT '未使用'   -- 未使用 / 已作废
);
```

## ⚙️ 配置文件

`data/config.json`：

```json
{
  "system": {
    "name": "班级积分防伪核销管理系统",
    "init_required": true,
    "encryption_salt": "<自动生成的32位hex>"
  },
  "printing": {
    "page_size": "A4",
    "rows_per_page": 5,
    "columns_per_page": 2
  },
  "paths": {
    "database": "./data/db/scores.db",
    "output": "./data/output"
  },
  "admin": {
    "username": "",
    "password": ""
  }
}
```

## 📄 开源协议

本项目基于 [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html) 开源。

---

<div align="center">

**Made with ❤️ for Education**

</div>
