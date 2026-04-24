FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run은 기본적으로 PORT 환경변수로 8080을 제공합니다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]