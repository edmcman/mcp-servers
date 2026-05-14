# MyFitnessPal MCP Server

Runs the [AdamWalt/myfitnesspal-mcp-python](https://github.com/AdamWalt/myfitnesspal-mcp-python) MCP server behind an ngrok tunnel, making it accessible remotely over SSE/HTTP.

## Architecture

```
ngrok edge → supergateway (HTTP:8000) → python -m mfp_mcp.server (stdio)
```

[supergateway](https://github.com/supercorp-ai/supergateway) bridges the stdio-only MCP server to an HTTP/SSE transport that ngrok tunnels.

## Prerequisites

- Docker and Docker Compose
- A MyFitnessPal account
- A free [ngrok](https://ngrok.com) account with an authtoken and a static domain

## Setup

### 1. Get ngrok credentials

1. Sign up at [ngrok.com](https://ngrok.com) (free)
2. Copy your authtoken from the [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Claim a free static domain at **Cloud Edge → Domains → New Domain**

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description |
|---|---|
| `MFP_USERNAME` | MyFitnessPal email address |
| `MFP_PASSWORD` | MyFitnessPal password |
| `NGROK_AUTHTOKEN` | Token from the ngrok dashboard |
| `NGROK_DOMAIN` | Your static domain, e.g. `your-name.ngrok-free.app` |

### 3. Build and run

```bash
docker compose build
docker compose up -d
```

Check logs:

```bash
docker compose logs -f
```

The MCP server is reachable at `https://<your-domain>/sse` once ngrok connects.

## Connecting to Claude

**Claude Code:**
```bash
claude mcp add myfitnesspal --transport sse https://your-domain.ngrok-free.app/sse
```

**Claude Desktop (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "myfitnesspal": {
      "url": "https://your-domain.ngrok-free.app/sse"
    }
  }
}
```

## Stopping

```bash
docker compose down
```
