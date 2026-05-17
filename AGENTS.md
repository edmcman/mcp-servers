# Agent Guide

## Architecture

```
ngrok (static domain)
  └─► nginx :80
        └─► <server-name>-mcp:<port>   (supergateway, streamableHttp)
              └─► python/node MCP server (stdio)
```

nginx does path-based routing so multiple MCP servers share one ngrok domain.

## Adding a new MCP server

**1. Add a service in `docker-compose.yml`:**
```yaml
  my-new-mcp:
    image: ...        # or build: ./my-new-mcp
    environment:
      - SOME_VAR=${SOME_VAR}
    restart: unless-stopped
```
Pick an unused internal port (8001, 8002, …) for supergateway.

**2. Add a location block in `nginx/nginx.conf`:**
```nginx
location /newname/ {
  rewrite ^/newname/(.*) /$1 break;
  proxy_pass http://my-new-mcp:8001;

  proxy_buffering           off;
  proxy_cache               off;
  proxy_read_timeout        3600s;
  proxy_set_header          Connection '';
  proxy_http_version        1.1;
  chunked_transfer_encoding on;
  add_header                X-Accel-Buffering no;
}
```
Add `my-new-mcp` to nginx's `depends_on` in `docker-compose.yml`.

**3. Apply:**
```bash
docker compose up -d --build
```

## MCP endpoint URL pattern

Each server is reachable at:
```
https://<NGROK_BASIC_AUTH>@<NGROK_DOMAIN>/<name>/mcp
```

The transport is `streamableHttp` (POST `/mcp`), not SSE.

## Environment variables (`.env`)

| Variable | Description |
|---|---|
| `NGROK_AUTHTOKEN` | ngrok auth token |
| `NGROK_DOMAIN` | Static ngrok domain |
| `NGROK_BASIC_AUTH` | `user:password` protecting the public endpoint |
| `MFP_USERNAME` | MyFitnessPal email |
| `MFP_PASSWORD` | MyFitnessPal password |

## Testing a server

```bash
source .env
curl -s -X POST "https://${NGROK_BASIC_AUTH}@${NGROK_DOMAIN}/<name>/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}'
```

A valid response contains `"serverInfo"` with the server name and version.

## Useful commands

```bash
docker compose up -d --build   # start / rebuild
docker compose down            # stop
docker compose logs -f         # stream all logs
docker compose logs -f nginx   # stream nginx logs only
```
