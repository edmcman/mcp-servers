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

## MyFitnessPal MCP Implementation Notes

### Diary Write Operations (Refactored 2026-05-17)

The MCP server (`mfp-mcp/src/mfp_mcp/server.py`) is a thin wrapper over `python-myfitnesspal`. Working write operations have been moved into the library (`python-myfitnesspal/myfitnesspal/client.py`).

**Working write tools:**
- `mfp_delete_diary_entry(meal, entry_index, date)` — deletes by meal + 0-based index. Calls `client.delete_diary_entry()`.
- `mfp_log_saved_meal(meal_name, diary_meal, date)` — logs a saved/custom meal. Calls `client.log_saved_meal()`.
- `mfp_add_food_to_diary(mfp_id, meal, date, quantity, unit)` — adds a food item to the diary. Calls `client.add_food_to_diary()`.
- `mfp_set_measurement(measurement, value)` — logs weight, body fat, etc.
- `mfp_set_goals(calories, protein, carbohydrates, fat)` — updates nutrition goals
- `mfp_create_food(...)` — creates a new food in the MFP database

**Listing saved meals (`mfp_get_saved_meals`):**
- Uses `client.get_meals_detailed()` which hits `/api/v1/foods/meals` (JSON API, requires NextAuth token).
- Returns up to 10 saved meals with `meal_id`, `description`, and `foods` array.
- Each food in the array has `food_id`, `serving_size`, `servings`, `nutrition`.

**Logging a saved meal (`mfp_log_saved_meal`) — BROKEN:**
- `get_meals_detailed()` works (returns saved meal groups via `/api/v1/foods/meals` JSON API, e.g. "Giant Turkey Sandwich").
- `log_saved_meal()` is broken: it scrapes `/food/add_to_diary` for the meal name, but that page lists individual favorite *food items* (e.g. "Applegate - Deli Sliced Oven Roasted Turkey"), not saved meal group names. So the name match always fails.
- Fix needed: find the correct endpoint or page that lists saved meal groups in a form that can be submitted, or use the meal_id from `get_meals_detailed()` directly.

**Adding food to diary (`mfp_add_food_to_diary`):**
- The library method `add_food_to_diary()` POSTs to `/food/add` with `food_entry[food_id]`, `food_entry[weight_id]`, `food_entry[meal_id]`, `food_entry[quantity]`, `food_entry[date]`, `ajax=true`.
- Requires `Authorization: Bearer {access_token}`, `X-CSRF-Token` (from meta tag on `/food/search`), `mfp-client-id`, `mfp-user-id` headers.
- Returns 204 on success (no body).
- Both old-format (small ints) and new-format (large ints) food IDs work.

**Setting water (`mfp_set_water`):**
- The library method `set_water()` POSTs to `/food/water` with `milliliters` and `date` params.
- Requires the same headers as `add_food_to_diary` (Authorization, X-CSRF-Token from meta tag, mfp-client-id, mfp-user-id).
- Returns 200 with `{"item": {"date": "...", "milliliters": ...}}` on success.
- The MCP tool accepts `cups` and converts to ml (1 cup = 236.588 ml).

**Known broken endpoints (do not use):**
- None currently known — all diary write tools are functional.

**Key technical learnings:**
1. **MyFitnessPal has two auth systems:**
   - NextAuth: `__Secure-next-auth.session-token` (used by most read APIs and JSON endpoints)
   - Rails legacy: `_mfp_session`, `remember_me` (required by `/food/remove`, `/food/add_favorites`, `/food/load_meals`)
2. **Rails endpoints require CSRF tokens** from `<meta name="csrf-token">`. DELETE requests must include `X-CSRF-Token` header; without it they redirect to login.
3. **Saved-meal pagination** (`/food/load_meals`) requires visiting `/food/add_to_diary?meal={i}&date={date}` first to establish server-side pagination state.
4. **Cookie domain scoping** — `browser_cookie3` loads cookies for `.myfitnesspal.com`, but the library's session must also set them on `www.myfitnesspal.com` for Rails endpoints. This is handled in `Client.__init__`.

## Useful commands

```bash
docker compose up -d --build   # start / rebuild
docker compose down            # stop
docker compose logs -f         # stream all logs
docker compose logs -f nginx   # stream nginx logs only
```
