FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gcc libffi-dev git ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY mfp-mcp /app
WORKDIR /app
RUN pip install -e .

RUN npm install -g supergateway

RUN useradd -m -u 1000 mcp
USER mcp

EXPOSE 8000
CMD ["supergateway", "--stdio", "python -m mfp_mcp.server", "--outputTransport", "streamableHttp", "--port", "8000", "--host", "0.0.0.0"]
