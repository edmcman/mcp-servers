# MyFitnessPal MCP Server

Runs the [AdamWalt/myfitnesspal-mcp-python](https://github.com/AdamWalt/myfitnesspal-mcp-python) MCP server behind a Cloudflare Tunnel, making it accessible remotely over SSE/HTTP.

## Architecture

```
Cloudflare Edge → cloudflared → supergateway (HTTP:8000) → python -m mfp_mcp.server (stdio)
```

[supergateway](https://github.com/supercorp-ai/supergateway) bridges the stdio-only MCP server to an HTTP/SSE transport that cloudflared can tunnel.

## Prerequisites

- Docker and Docker Compose
- A MyFitnessPal account
- A [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) with a token

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|---|---|
| `MFP_USERNAME` | MyFitnessPal email address |
| `MFP_PASSWORD` | MyFitnessPal password |
| `CLOUDFLARE_TUNNEL_TOKEN` | Token from the Cloudflare dashboard |

### 2. Configure the Cloudflare Tunnel

In the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/), set your tunnel's public hostname **Service URL** to:

```
http://mfp-mcp:8000
```

### 3. Build and run

```bash
docker compose build
docker compose up -d
```

Check logs:

```bash
docker compose logs -f
```

The `cloudflared` logs will show `Connection established` once the tunnel is live. The MCP server is then reachable at your configured public hostname.

## Stopping

```bash
docker compose down
```
