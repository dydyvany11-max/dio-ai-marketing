# Frontend (React)

Базовый интерфейс для:
- `POST /vk/group/analyze`
- `POST /vk/posts/generate`

## Запуск

1. Подними backend на `http://127.0.0.1:8000`
2. В новом терминале:

```bash
cd frontend
npm install
npm run dev
```

Откроется `http://127.0.0.1:5173`.

Vite proxy уже настроен, поэтому запросы `/vk/...` идут в backend без CORS-настроек.
