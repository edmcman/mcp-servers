# MCP Servers

Hosts one or more MCP servers behind a single ngrok tunnel, accessible remotely over HTTP.

## Architecture

```
ngrok (static domain)
  └─► nginx :80  (path-based routing)
        └─► <server>-mcp:<port>  (supergateway, streamableHttp)
              └─► MCP server process (stdio)
```

[supergateway](https://github.com/supercorp-ai/supergateway) bridges each stdio MCP server to HTTP. nginx routes different URL path prefixes to different backends, so all servers share one ngrok domain.

## Servers

| Path prefix | Server |
|---|---|
| `/mfp` | [myfitnesspal-mcp-python](https://github.com/AdamWalt/myfitnesspal-mcp-python) |

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
| `NGROK_BASIC_AUTH` | Credentials to protect the endpoint, e.g. `username:somepassword` |

### 3. Build and run

```bash
docker compose build
docker compose up -d
```

Check logs:

```bash
docker compose logs -f
```

The MFP server is reachable at `https://<your-domain>/mfp/mcp` once ngrok connects.

## Connecting to Claude

**Claude Code:**
```bash
claude mcp add myfitnesspal --transport http https://username:somepassword@your-domain.ngrok-free.app/mfp/mcp
```

**Claude Desktop (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "myfitnesspal": {
      "url": "https://username:somepassword@your-domain.ngrok-free.app/mfp/mcp"
    }
  }
}
```

## Stopping

```bash
docker compose down
```
