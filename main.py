import os
import secrets
from typing import Any
from urllib.parse import urlencode
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
load_dotenv()

VK_CLIENT_ID = os.getenv("VK_CLIENT_ID", "")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET", "")
VK_REDIRECT_URI = os.getenv("VK_REDIRECT_URI", "http://127.0.0.1:8000/auth/vk/callback")
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.199")
SESSION_SECRET = os.getenv("SESSION_SECRET", "project-dio-marketing")
VK_OAUTH_AUTHORIZE_URL = "https://oauth.vk.com/authorize"
VK_OAUTH_ACCESS_TOKEN_URL = "https://oauth.vk.com/access_token"
VK_API_URL = "https://api.vk.com/method"
app = FastAPI(
    title="VK OAuth Demo",
    version="1.0.0",
    description="Минимальный backend для авторизации через VK и получения access_token",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="vk_demo_session",
    max_age=60 * 60 * 24,
    same_site="lax",
    https_only=False,  # для локального теста
)
def ensure_vk_settings() -> None:
    if not VK_CLIENT_ID or not VK_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Нужно задать VK_CLIENT_ID и VK_CLIENT_SECRET в .env",
        )


async def vk_api_call(method: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{VK_API_URL}/{method}",
            params={**params, "v": VK_API_VERSION},
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"VK API HTTP error: {response.status_code}",
        )

    data = response.json()

    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])

    return data["response"]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> str:
    token = request.session.get("vk_access_token")
    user = request.session.get("vk_user")

    login_block = """
    <a href="/auth/vk/login">
        <button style="padding:10px 16px; font-size:16px;">Войти через VK</button>
    </a>
    """

    user_block = ""
    if token:
        user_block = f"""
        <h3>Уже авторизован</h3>
        <pre>{user}</pre>
        <p><a href="/auth/vk/me">Посмотреть профиль через VK API</a></p>
        <p><a href="/auth/logout">Выйти</a></p>
        """

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>VK OAuth Demo</title>
      </head>
      <body style="font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto;">
        <h1>VK OAuth Demo</h1>
        <p>Тестовый backend-only вход через VK.</p>
        {login_block}
        <hr />
        {user_block}
        <p><a href="/docs">Swagger</a></p>
      </body>
    </html>
    """


@app.get("/auth/vk/login")
async def vk_login(request: Request) -> RedirectResponse:
    """
    Редиректим пользователя в VK на страницу авторизации.
    """
    ensure_vk_settings()

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "response_type": "code",
        "scope": "groups,wall,offline",
        "v": VK_API_VERSION,
        "state": state,
    }

    auth_url = f"{VK_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@app.get("/auth/vk/callback")
async def vk_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """
    VK вернет сюда пользователя после логина.
    Здесь меняем code на access_token.
    """
    ensure_vk_settings()

    if error:
        raise HTTPException(
            status_code=400,
            detail={
                "error": error,
                "error_description": error_description,
            },
        )

    if not code:
        raise HTTPException(status_code=400, detail="VK не вернул code")

    session_state = request.session.get("oauth_state")
    if not session_state or session_state != state:
        raise HTTPException(status_code=400, detail="Некорректный state")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_response = await client.get(
            VK_OAUTH_ACCESS_TOKEN_URL,
            params={
                "client_id": VK_CLIENT_ID,
                "client_secret": VK_CLIENT_SECRET,
                "redirect_uri": VK_REDIRECT_URI,
                "code": code,
                "v": VK_API_VERSION,
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка обмена code->token: HTTP {token_response.status_code}",
        )

    token_data = token_response.json()

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=token_data)

    access_token = token_data.get("access_token")
    user_id = token_data.get("user_id")
    expires_in = token_data.get("expires_in")
    email = token_data.get("email")

    if not access_token:
        raise HTTPException(status_code=400, detail="VK не вернул access_token")

    request.session["vk_access_token"] = access_token
    request.session["vk_user_id"] = user_id
    request.session["vk_email"] = email
    request.session["vk_expires_in"] = expires_in

    # Сразу дернем профиль, чтобы видеть, что токен рабочий
    profile = await vk_api_call(
        "users.get",
        {
            "access_token": access_token,
            "user_ids": user_id,
            "fields": "photo_100,screen_name",
        },
    )

    user_info = profile[0] if profile else {}
    request.session["vk_user"] = user_info

    # Для твоего теста возвращаю токен в JSON.
    # В проде токен так наружу не отдают.
    return JSONResponse(
        {
            "message": "VK login success",
            "access_token": access_token,
            "user_id": user_id,
            "expires_in": expires_in,
            "email": email,
            "profile": user_info,
            "next": {
                "profile_check": "/auth/vk/me",
                "logout": "/auth/logout",
                "swagger": "/docs",
            },
        }
    )


@app.get("/auth/vk/me")
async def vk_me(request: Request):
    access_token = request.session.get("vk_access_token")
    user_id = request.session.get("vk_user_id")

    if not access_token or not user_id:
        raise HTTPException(status_code=401, detail="Пользователь не авторизован через VK")

    profile = await vk_api_call(
        "users.get",
        {
            "access_token": access_token,
            "user_ids": user_id,
            "fields": "photo_100,screen_name,domain",
        },
    )

    return {
        "authorized": True,
        "user": profile[0] if profile else None,
    }


@app.get("/auth/session")
async def auth_session(request: Request):
    """
    Просто посмотреть, что лежит в сессии.
    """
    return {
        "vk_user_id": request.session.get("vk_user_id"),
        "vk_email": request.session.get("vk_email"),
        "has_access_token": bool(request.session.get("vk_access_token")),
        "vk_user": request.session.get("vk_user"),
    }


@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "logout ok"}