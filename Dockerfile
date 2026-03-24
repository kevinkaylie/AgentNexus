FROM python:3.11-slim

WORKDIR /app

# 只复制依赖文件，利用 Docker layer 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 非 root 用户运行
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 9000

CMD ["python", "main.py", "relay", "start"]
