# MCP Servers

Hosts one or more MCP servers behind a single ngrok tunnel, protected by OAuth 2.1.

## Architecture

```
ngrok (static domain)
  └─► nginx :80  (path-based routing)
        ├─► hydra :4444/:4445  (OAuth 2.1, DCR, JWKS, tokens)
        └─► oauth-proxy :8080  (login/consent UI + JWT validation)
              └─► <server>-mcp:<port>  (supergateway, streamableHttp)
                    └─► MCP server process (stdio)
```

[supergateway](https://github.com/supercorp-ai/supergateway) bridges each stdio MCP server to HTTP. nginx routes OAuth protocol endpoints to [Ory Hydra](https://www.ory.sh/hydra/) and MCP traffic through `oauth-proxy`, so all servers share one ngrok domain while MCP endpoints require valid Bearer tokens.

Hydra provides OAuth 2.1 authorization, PKCE, dynamic client registration (DCR), JWKS, and JWT access tokens. `oauth-proxy` provides the simple login/consent UI, reads users from `oauth/hydra/users.yml`, and validates JWTs before forwarding MCP requests.

## Endpoint

MyFitnessPal MCP is available at:

```text
https://<your-domain>/mfp/mcp
```

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
| `OAUTH_PASSWORD` | Password for the OAuth login UI user `ed` |
| `HYDRA_DSN` | Hydra database DSN, normally `sqlite:///data/hydra.db?mode=rwc&_fk=true` |
| `HYDRA_SYSTEM_SECRET` | 32+ character Hydra system secret |

Users are configured in `oauth/hydra/users.yml`. Passwords can be plaintext or bcrypt hashes; bcrypt is preferred.

```bash
cp oauth/hydra/users.example.yml oauth/hydra/users.yml
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

The MFP server is reachable once ngrok connects. Do not put credentials in the URL; OAuth handles authentication.

## Connecting Clients

Use the MCP endpoint URL:

```text
https://<your-domain>/mfp/mcp
```

Clients that support remote MCP OAuth, such as ChatGPT connectors and Claude.ai integrations, should discover OAuth metadata automatically, register via DCR, then redirect to the login UI. The configured username is `ed`; the password is `OAUTH_PASSWORD` from `.env`.

Hydra remembers successful browser logins for 24 hours, so adding a second client in the same browser may not prompt for the password again.

## Claude Code

Claude Code's HTTP MCP support may not perform the same OAuth connector flow as Claude.ai. If using Claude Code, add the unauthenticated URL only if your client supports OAuth for remote MCP:

```bash
claude mcp add myfitnesspal --transport http https://your-domain.ngrok-free.app/mfp/mcp
```

## Stopping

```bash
docker compose down
```
