FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（matplotlib 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Railway 会提供 PORT 环境变量，我们用 6789 作为默认
EXPOSE 6789
CMD ["python", "app.py"]
