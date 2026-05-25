FROM python:3.11-slim

WORKDIR /app

# 빌드 캐시 활용: 의존성 먼저 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]
