# Agent Guide

## Architecture

```
ngrok (static domain, no auth)
  └─► nginx :80
        ├─► oauth-proxy :8080 (token validation + RS metadata + Hydra login/consent UI)
        │     └─► <server-name>-mcp:<port> (supergateway, streamableHttp)
        │           └─► python/node MCP server (stdio)
        └─► hydra :4444/:4445 (OAuth 2.1 Authorization Server + DCR + JWKS + tokens)
```

nginx routes OAuth protocol endpoints to Hydra, login/consent and MCP endpoints through oauth-proxy. The proxy validates JWT Bearer tokens (JWKS) before forwarding to supergateway.

## OAuth 2.1 Setup (Hydra)

- **Hydra** (`oryd/hydra:v2.3.0`) is the Authorization Server with PKCE, native DCR, AS/OIDC metadata, JWKS, and tokens.
- **oauth-proxy** (`oauth/oauth-proxy/`) is the Resource Server and login provider: validates JWTs, serves `/.well-known/oauth-protected-resource`, and handles Hydra login/consent callbacks.
- Users are defined in `oauth/hydra/users.yml`; passwords can be plaintext or bcrypt hashes. Use `oauth/hydra/users.example.yml` as the template, and do not commit the real `users.yml`.
- DCR is exposed at `/oauth2/register` for dynamic client registration (ChatGPT uses this).
- SQLite storage persists in `./hydra-data/hydra.db`.
- Hydra must issue JWT access tokens (`strategies.access_token: jwt`) so oauth-proxy can validate MCP Bearer tokens locally via JWKS.
- Password change: generate a new bcrypt hash with `python3 -c "import bcrypt; print(bcrypt.hashpw(b'PASSWORD', bcrypt.gensalt()).decode())"` and update `oauth/hydra/users.yml`, then rebuild/restart `oauth-proxy`.

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

**2. Add the upstream to `oauth/oauth-proxy/app/main.py`:**
```python
UPSTREAMS = {
    "/mfp/": os.getenv("MFP_UPSTREAM_URL", "http://mfp-mcp:8000"),
    "/newname/": os.getenv("NEWNAME_UPSTREAM_URL", "http://my-new-mcp:8001"),
}
```
And add a route handler (copy the `proxy_mfp` pattern).

**3. Add a location block in `nginx/nginx.conf`:**
```nginx
location /newname/ {
  proxy_pass http://oauth-proxy:8080;

  proxy_buffering           off;
  proxy_cache               off;
  proxy_read_timeout        3600s;
  proxy_set_header          Connection '';
  proxy_http_version        1.1;
  chunked_transfer_encoding on;
  add_header                X-Accel-Buffering no;
}
```
Add `my-new-mcp` to nginx's and oauth-proxy's `depends_on` in `docker-compose.yml`.

**4. Apply:**
```bash
docker compose up -d --build
```

## MCP endpoint URL pattern

Each server is reachable at:
```
https://<NGROK_DOMAIN>/<name>/mcp
```

No credentials in the URL — OAuth 2.1 handles authentication. The transport is `streamableHttp` (POST `/mcp`), not SSE.

## Environment variables (`.env`)

| Variable | Description |
|---|---|
| `NGROK_AUTHTOKEN` | ngrok auth token |
| `NGROK_DOMAIN` | Static ngrok domain |
| `OAUTH_PASSWORD` | Password for Hydra login UI |
| `HYDRA_DSN` | Hydra database DSN, normally `sqlite:///data/hydra.db?mode=rwc&_fk=true` |
| `HYDRA_SYSTEM_SECRET` | Hydra system secret, 32+ random characters |
| `MFP_USERNAME` | MyFitnessPal email |
| `MFP_PASSWORD` | MyFitnessPal password |

## Testing a server

Unauthenticated requests return 401:
```bash
source .env
curl -s -X POST "https://${NGROK_DOMAIN}/mfp/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

Full OAuth flow requires a browser or programmatic client (PKCE + authorization code exchange).

## MyFitnessPal MCP Implementation Notes

### Diary Write Operations (Refactored 2026-05-17)

The MCP server (`mfp-mcp/src/mfp_mcp/server.py`) is a thin wrapper over `python-myfitnesspal`. Working write operations have been moved into the library (`python-myfitnesspal/myfitnesspal/client.py`).

**Working write tools:**
- `mfp_delete_diary_entry(meal, entry_index, date)` — deletes by meal + 0-based index. Calls `client.delete_diary_entry()`.
- `mfp_log_saved_meal(meal_name, diary_meal, date)` — logs a saved/custom meal. Calls `client.log_saved_meal()`.
- `mfp_add_food_to_diary(mfp_id, meal, date, quantity, weight_id)` — adds a food item to the diary. Pass `weight_id` from `mfp_search_food` results. Calls `client.add_food_to_diary()`.
- `mfp_set_measurement(measurement, value)` — logs weight, body fat, etc.
- `mfp_set_goals(calories, protein, carbohydrates, fat)` — updates nutrition goals
- `mfp_create_food(...)` — creates a new food in the MFP database

**Listing saved meals (`mfp_get_saved_meals`):**
- Uses `client.get_meals_detailed()` which hits `/api/v1/foods/meals` (JSON API, requires NextAuth token).
- Returns up to 10 saved meals with `meal_id`, `description`, and `foods` array.
- Each food in the array has `food_id`, `serving_size`, `servings`, `nutrition`.

**Logging a saved meal (`mfp_log_saved_meal`) — WORKING:**
- Calls `client.log_saved_meal(meal_name, diary_meal, date)` in the library.
- Flow: GET `/food/add_to_diary?meal={meal_index}&date=...` to prime Rails session state and extract `authenticity_token`, then call `load_meals()` to paginate saved meal groups, find by name, POST to `/food/add_favorites`.
- **Critical**: `Origin` header must be `https://www.myfitnesspal.com` (no trailing slash) — trailing slash causes the server to return a full HTML page instead of the AJAX fragment. Fixed by removing trailing slash from `BASE_URL_SECURE`.
- **Critical**: pagination requires incrementing both `base_index` and `page` together (e.g. `base_index=25, page=2`); sending `page=1` always returns the same first page regardless of `base_index`.
- The `/food/load_meals` AJAX endpoint returns saved meal groups (not individual food favorites) when properly primed.

**Adding food to diary (`mfp_add_food_to_diary`):**
- The library method `add_food_to_diary()` POSTs to `/food/add` with `food_entry[food_id]`, `food_entry[weight_id]`, `food_entry[meal_id]`, `food_entry[quantity]`, `food_entry[date]`, `ajax=true`.
- Requires `Authorization: Bearer {access_token}`, `X-CSRF-Token` (from meta tag on `/food/search`), `mfp-client-id`, `mfp-user-id` headers.
- Returns 204 on success (no body).
- **CRITICAL — ID formats**: `/food/add` only works with old-format (~10-digit) food and weight IDs. New-format (15-digit) IDs return 204 but silently do nothing.
- **ID sources**: `mfp_search_food` HTML scrape returns `data-original-id` (old-format) as `mfp_id` and `data-weight-ids` (old-format) as `weight_ids`. Always use these — do NOT use the `data-external-id` or IDs from the v2 (`api.myfitnesspal.com`) API.
- **v2 API is mobile-only**: `api.myfitnesspal.com/v2/foods/{id}` only accepts new-format IDs and returns new-format serving size IDs — these cannot be used with `/food/add`.

**Setting water (`mfp_set_water`):**
- The library method `set_water()` POSTs to `/food/water` with `milliliters` and `date` params.
- Requires the same headers as `add_food_to_diary` (Authorization, X-CSRF-Token from meta tag, mfp-client-id, mfp-user-id).
- Returns 200 with `{"item": {"date": "...", "milliliters": ...}}` on success.
- The MCP tool accepts `cups` and converts to ml (1 cup = 236.588 ml).

**Listing recent/frequent/my foods (added 2026-05-18):**
- Three new read tools: `mfp_get_recent_foods`, `mfp_get_frequent_foods`, `mfp_get_my_foods`.
- All backed by `client._load_food_tab(endpoint_path, meal_index)` — a shared helper extracted from `load_meals`.
- Endpoints: `POST /food/load_recent`, `POST /food/load_most_used` (frequent), `POST /food/load_my_foods`.
- All use identical request shape: `meal`, `base_index`, `page` form params + `X-CSRF-Token` + `X-Requested-With: XMLHttpRequest`. CSRF is primed by GETting `/food/add_to_diary?meal={meal_index}` first.
- HTML response: `//tr[contains(@class,"favorite")]` rows — same structure across all tabs.
- **Frequent tab naming quirk**: The MFP "Frequent" UI tab maps to `load_most_used` on the server, not `load_frequent`. The tab's JavaScript does `if (categoryName === 'frequent') { categoryName = 'most_used'; }`.
- **Frequent foods are pre-embedded**: Page 1 of frequent foods is inline in the initial `GET /user/{username}/diary/add` HTML (JS sets `loaded['frequent1'] = true` at init). Subsequent pages use `POST /food/load_most_used`. Our `_load_food_tab` implementation always POSTs for page 1 as well, which returns the same data — this is intentional and correct.
- Returns `list[dict]` with keys: `food_id`, `weight_id`, `name`, `index`. IDs are old-format (~10-digit) and can be passed directly to `mfp_add_food_to_diary`.

**Known broken endpoints (do not use):**
- None currently known — all diary write tools are functional.

**Key technical learnings:**
1. **MyFitnessPal has two auth systems:**
   - NextAuth: `__Secure-next-auth.session-token` (used by most read APIs and JSON endpoints)
   - Rails legacy: `_mfp_session`, `remember_me` (required by `/food/remove`, `/food/add_favorites`, `/food/load_meals`)
2. **Rails endpoints require CSRF tokens** from `<meta name="csrf-token">`. DELETE requests must include `X-CSRF-Token` header; without it they redirect to login.
3. **Food-tab pagination** (`/food/load_meals`, `/food/load_recent`, `/food/load_most_used`, `/food/load_my_foods`) requires visiting `/food/add_to_diary?meal={i}&date={date}` first to establish server-side state and extract the CSRF token. Pagination requires incrementing both `base_index` and `page` together (not just `base_index`). The `Origin` header must be `https://www.myfitnesspal.com` with no trailing slash — a trailing slash causes the endpoint to return the full page instead of the AJAX fragment.
4. **Cookie domain scoping** — `browser_cookie3` loads cookies for `.myfitnesspal.com`, but the library's session must also set them on `www.myfitnesspal.com` for Rails endpoints. This is handled in `Client.__init__`.
5. **MFP has two parallel food ID systems**: old-format (~10-digit, e.g. `2744666713`) used by the Rails website, and new-format (~15-digit, e.g. `133055560789037`) used by the mobile v2 API. The HTML search page exposes both via `data-original-id` (old) and `data-external-id` (new). `mfp_search_food` returns both as `mfp_id` (old) and `external_id` (new). Use `mfp_id` for write operations (`mfp_add_food_to_diary`); use `external_id` for `mfp_get_food_details`.

## Useful commands

```bash
docker compose up -d --build   # start / rebuild
docker compose down            # stop
docker compose logs -f         # stream all logs
docker compose logs -f nginx   # stream nginx logs only
```
