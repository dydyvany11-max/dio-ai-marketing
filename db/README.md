# База данных и хранилища

## Быстрый старт (Docker)

1. Скопировать `.env.example` в `.env` и при необходимости изменить пароли/порты.
2. Запуск:

```bash
docker compose up -d
```

После старта Postgres автоматически применит схему из `db/init/001-schema.sql`.

## Сервис

- Postgres: порт из `POSTGRES_PORT`
