# Dockerfile — Python service for Next Level Auto
FROM python:3.12-slim

WORKDIR /app

COPY python-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY python-service/ .
COPY config.yaml .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
