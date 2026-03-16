from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["VK ID"])


@router.get("/vkid/login", response_class=HTMLResponse)
def vkid_login_page():
    html = """
    <!doctype html>
    <html lang="ru">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>VK ID Login</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 32px; background: #f6f7f8; }
          .card { max-width: 520px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 6px 24px rgba(0,0,0,.08); }
          h1 { font-size: 20px; margin: 0 0 12px; }
          p { color: #444; }
          a.button { display: inline-block; background: #2787f5; color: #fff; padding: 12px 18px; border-radius: 8px; text-decoration: none; font-weight: 600; }
          .hint { margin-top: 12px; font-size: 12px; color: #777; }
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Вход через VK ID</h1>
          <p>Нажми кнопку, чтобы авторизоваться. После входа ты вернёшься с токеном.</p>
          <a class="button" href="/vkid/start">Войти через VK ID</a>
          <div class="hint">Если ты видишь CORS в Swagger — используй эту страницу.</div>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(content=html)
