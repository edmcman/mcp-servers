FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY python-myfitnesspal /python-myfitnesspal
RUN pip install -e /python-myfitnesspal

COPY mfp-mcp /app
WORKDIR /app
RUN pip install -e . && pip install mcp-proxy

RUN useradd -m -u 1000 mcp
USER mcp

EXPOSE 8000
CMD ["mcp-proxy", "--host", "0.0.0.0", "--port", "8000", "--pass-environment", "--stateless", "--", "python", "-m", "mfp_mcp.server"]