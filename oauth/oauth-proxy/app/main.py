import os
import logging

import bcrypt
import httpx
import jwt
import yaml
from jwt import PyJWKClient
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, Response, HTMLResponse, RedirectResponse

logger = logging.getLogger("oauth-proxy")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="MCP OAuth Proxy")

NGROK_DOMAIN = os.getenv("NGROK_DOMAIN")
HYDRA_ADMIN_URL = os.getenv("HYDRA_ADMIN_URL", "http://hydra:4445")
HYDRA_PUBLIC_URL = os.getenv("HYDRA_PUBLIC_URL", "http://hydra:4444")
ISSUER_URL = f"https://{NGROK_DOMAIN}"
JWKS_URL = f"{HYDRA_PUBLIC_URL}/.well-known/jwks.json"
RESOURCE_URL = f"{ISSUER_URL}/.well-known/oauth-protected-resource"
USERS_FILE = os.getenv("USERS_FILE", "/config/users.yml")

UPSTREAMS = {
    "/mfp/": os.getenv("MFP_UPSTREAM_URL", "http://mfp-mcp:8000"),
}

jwks_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)

def _load_users() -> dict:
    with open(USERS_FILE) as f:
        return {u["username"]: u for u in yaml.safe_load(f)["users"]}


def _check_password(users: dict, username: str, password: str) -> bool:
    u = users.get(username)
    if not u:
        return False
    stored = u["password"]
    if stored.startswith("$"):
        return bcrypt.checkpw(password.encode(), stored.encode())
    return stored == password


def _unauthorized() -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource_metadata="{RESOURCE_URL}"'},
    )


# --- RFC 9728: Protected Resource Metadata ---

@app.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata():
    return JSONResponse({
        "resource": RESOURCE_URL,
        "authorization_servers": [ISSUER_URL],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
    })


async def _authorization_server_metadata() -> JSONResponse:
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{HYDRA_PUBLIC_URL}/.well-known/openid-configuration")
        r.raise_for_status()
        data = r.json()
    data["registration_endpoint"] = f"{ISSUER_URL}/oauth2/register"
    data["scopes_supported"] = sorted(set(data.get("scopes_supported", [])) | {"email", "profile"})
    return JSONResponse(data)


@app.get("/.well-known/openid-configuration")
async def openid_configuration():
    return await _authorization_server_metadata()


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    return await _authorization_server_metadata()


# --- Login UI (Hydra login provider) ---

LOGIN_HTML = """<!DOCTYPE html>
<html><head><title>Sign in</title>
<style>
  body {{ font-family: sans-serif; display: flex; justify-content: center; padding-top: 80px; background: #f5f5f5; }}
  form {{ background: white; padding: 32px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1); width: 320px; }}
  h2 {{ margin: 0 0 24px; }}
  input {{ width: 100%; padding: 8px; margin: 6px 0 16px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }}
  button {{ width: 100%; padding: 10px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 15px; }}
  .error {{ color: red; margin-bottom: 12px; }}
</style></head>
<body><form method="POST">
  <h2>Sign in</h2>
  {error}
  <input type="hidden" name="login_challenge" value="{challenge}">
  <label>Username</label><input name="username" autofocus>
  <label>Password</label><input name="password" type="password">
  <button type="submit">Sign in</button>
</form></body></html>"""


@app.get("/auth/login", response_class=HTMLResponse)
async def login_get(login_challenge: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/login", params={"login_challenge": login_challenge})
        data = r.json()
    if data.get("skip"):
        subject = data["subject"]
        async with httpx.AsyncClient() as c:
            r = await c.put(
                f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/login/accept",
                params={"login_challenge": login_challenge},
                json={"subject": subject},
            )
            redirect_to = r.json()["redirect_to"]
        return RedirectResponse(redirect_to)
    return HTMLResponse(LOGIN_HTML.format(challenge=login_challenge, error=""))


@app.post("/auth/login", response_class=HTMLResponse)
async def login_post(login_challenge: str = Form(...), username: str = Form(...), password: str = Form(...)):
    users = _load_users()
    if not _check_password(users, username, password):
        return HTMLResponse(LOGIN_HTML.format(
            challenge=login_challenge,
            error='<div class="error">Invalid username or password.</div>',
        ))
    async with httpx.AsyncClient() as c:
        r = await c.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/login/accept",
            params={"login_challenge": login_challenge},
            json={"subject": username, "remember": True, "remember_for": 86400},
        )
        redirect_to = r.json()["redirect_to"]
    return RedirectResponse(redirect_to, status_code=303)


# --- Consent (auto-accept) ---

@app.get("/auth/consent")
async def consent_get(consent_challenge: str):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent", params={"consent_challenge": consent_challenge})
        data = r.json()
    requested_scope = data.get("requested_scope", [])
    subject = data.get("subject", "")
    users = _load_users()
    user = users.get(subject, {})
    async with httpx.AsyncClient() as c:
        r = await c.put(
            f"{HYDRA_ADMIN_URL}/admin/oauth2/auth/requests/consent/accept",
            params={"consent_challenge": consent_challenge},
            json={
                "grant_scope": requested_scope,
                "grant_access_token_audience": data.get("requested_access_token_audience", []),
                "remember": True,
                "remember_for": 86400,
                "session": {
                    "id_token": {
                        "email": user.get("email", subject),
                        "name": subject,
                    }
                },
            },
        )
        redirect_to = r.json()["redirect_to"]
    return RedirectResponse(redirect_to)


# --- Token validation + MCP proxy ---

async def _validate_token(auth_header: str) -> dict:
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=ISSUER_URL,
            options={"require": ["exp", "iss", "sub"], "verify_aud": False},
        )
        return claims
    except (jwt.InvalidTokenError, Exception) as e:
        logger.warning(f"Token validation failed: {e}")
        return None


@app.api_route("/mfp/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_mfp(request: Request, path: str):
    auth_header = request.headers.get("Authorization", "")
    claims = await _validate_token(auth_header)
    if not claims:
        return _unauthorized()

    upstream = UPSTREAMS["/mfp/"]
    target_url = f"{upstream}/{path}"

    body = await request.body()
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length", "transfer-encoding", "connection")
    }

    async with httpx.AsyncClient(timeout=3600.0) as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            content=body,
        )

    response_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in ("transfer-encoding", "connection", "content-encoding")
    }

    return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)


@app.get("/health")
async def health():
    return {"status": "ok"}
