# 箱庭島 NAS server — Python 3.12 slim
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HAKONIWA_DATA_DIR=/data \
    HAKONIWA_HOST=0.0.0.0 \
    HAKONIWA_PORT=8787

# Shared gameplay rules live in ../hakoniwa (build context = repo root).
COPY hakoniwa/ /app/hakoniwa/
COPY hakoniwa_server/ /app/hakoniwa_server/

RUN pip install --no-cache-dir -r /app/hakoniwa_server/requirements.txt

VOLUME ["/data"]
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3)"

CMD ["python", "-m", "hakoniwa_server"]
