# Multi-stage image shared by the gateway, ledger and agent_worker services.
# The command is chosen per service in docker-compose.yml.
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 --prefix=/install -r requirements.txt

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /install /usr/local
COPY services ./services
COPY infra ./infra
RUN useradd --create-home appuser
USER appuser
EXPOSE 8001 8002
CMD ["uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8001"]
