FROM python:3.12-slim

# 安装系统依赖（libzbar0 用于条码识别）
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY main.py .
COPY run.py .
COPY templates/ ./templates/
COPY static/ ./static/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# 创建数据目录
RUN mkdir -p /app/data/db /app/data/output

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
