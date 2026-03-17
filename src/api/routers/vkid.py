from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from src.api.config import PROJECT_ROOT, is_vkid_configured, load_vkid_settings
from src.api.schemas import VKIDAuthResponse

router = APIRouter(prefix="/vkid", tags=["VK ID"])

_VKID_TOKEN_PATH = Path(os.getenv("VKID_TOKEN_PATH", str(PROJECT_ROOT / "vkid_token.json")))


def _save_vk_token(payload: VKIDAuthResponse) -> None:
    data = {
        "access_token": payload.access_token,
        "expires_in": payload.expires_in,
        "user_id": payload.user_id,
        "scope": payload.scope,
    }
    _VKID_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _VKID_TOKEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_vk_token() -> str | None:
    if not _VKID_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(_VKID_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token.strip() else None


@router.get(
    "/login",
    response_class=HTMLResponse,
    summary="VK ID login page (SDK)",
)
def vkid_login_page():
    if not is_vkid_configured():
        raise HTTPException(status_code=400, detail="VK ID is not configured")

    settings = load_vkid_settings()
    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VK ID Login</title>
</head>
<body style="font-family:Arial, sans-serif; padding: 24px;">
  <h2>Login with VK ID</h2>
  <div id="vkid-container"></div>

  <script src="https://unpkg.com/@vkid/sdk@<3.0.0/dist-sdk/umd/index.js"></script>
  <script>
    if (!('VKIDSDK' in window)) {{
      document.getElementById('vkid-container').innerText = 'VK ID SDK failed to load';
    }} else {{
      const VKID = window.VKIDSDK;
      VKID.Config.init({{
        app: {settings.app_id},
        redirectUrl: '{settings.redirect_uri}',
        responseMode: VKID.ConfigResponseMode.Callback,
        source: VKID.ConfigSource.LOWCODE,
        scope: '{settings.scope}',
      }});

      const oneTap = new VKID.OneTap();
      oneTap.render({{
        container: document.getElementById('vkid-container'),
        showAlternativeLogin: true,
      }})
      .on(VKID.WidgetEvents.ERROR, function (err) {{
        console.error('VKID widget error', err);
      }})
      .on(VKID.OneTapInternalEvents.LOGIN_SUCCESS, function (payload) {{
        const code = payload.code;
        const deviceId = payload.device_id;

        VKID.Auth.exchangeCode(code, deviceId)
          .then(function (data) {{
            return fetch('/vkid/store', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(data)
            }});
          }})
          .then(function (resp) {{
            if (!resp.ok) throw new Error('Failed to store token');
            return resp.json();
          }})
          .then(function () {{
            document.body.innerHTML = '<h2>VK ID auth complete</h2><p>Token saved on server.</p>';
          }})
          .catch(function (err) {{
            console.error('VKID auth error', err);
            alert('VK ID authorization error');
          }});
      }});
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.get(
    "/callback",
    response_class=HTMLResponse,
    summary="VK ID callback landing",
)
def vkid_callback_page():
    html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VK ID Callback</title>
</head>
<body style="font-family:Arial, sans-serif; padding: 24px;">
  <h2>VK ID callback</h2>
  <p>You can close this page and return.</p>
</body>
</html>
"""
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.post(
    "/store",
    response_model=VKIDAuthResponse,
    summary="Store VK ID token on server",
)
def vkid_store(payload: VKIDAuthResponse):
    _save_vk_token(payload)
    return payload


@router.get(
    "/status",
    summary="VK ID token status",
)
def vkid_status():
    token = _load_vk_token()
    return {"authorized": bool(token), "token_path": str(_VKID_TOKEN_PATH)}
