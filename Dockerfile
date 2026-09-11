# Dockerfile for Next Level Auto Python agentic service
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY config/ config/

# Environment
ENV PYTHONPATH=/app/src
ENV PORT=8080

EXPOSE 8080

# Run
CMD ["python", "-m", "uvicorn", "src.service.main:app", "--host", "0.0.0.0", "--port", "8080"]
