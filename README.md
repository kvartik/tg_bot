# Kyberion Task Bot

Telegram-бот для управления задачами сети киберклубов. Подробная спека — в [CLAUDE.md](CLAUDE.md).

## Запуск (Docker, рекомендуемый)

```bash
cp .env.example .env   # вписать BOT_TOKEN, OWNER_BOT_TOKEN, OWNER_TG_ID, POSTGRES_PASSWORD
docker compose up -d --build
```

Поднимает Postgres 16 + бота. Данные — в volume `pgdata`,
ежедневные бэкапы pg_dump (4:30, хранятся 14 дней) — в `./backups/`.

Ботов два: основной (задачи, смены, рутина) и owner-бот (клубы, приглашение
управляющих, статистика) — оба токена у [@BotFather](https://t.me/BotFather).
Свой Telegram ID — у [@userinfobot](https://t.me/userinfobot).

## Локальная разработка без Docker

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env       # вписать токены; DATABASE_URL — свой Postgres
set -a; source .env; set +a
.venv/bin/python -m kyberion_bot.bot
```

Для быстрых экспериментов можно указать `DATABASE_URL=sqlite+aiosqlite:///kyberion.db`.

## Первые шаги после запуска

1. Владелец пишет **owner-боту** `/start` (доступ только у `OWNER_TG_ID`)
2. Owner-бот: «🏢 Клубы» → создать клуб
3. Owner-бот: «👥 Управляющие» → клуб → одноразовая инвайт-ссылка на управляющего.
   Чтобы самому вести клуб — перейдите по этой ссылке сами: в основном боте вы
   станете обычным управляющим
4. Основной бот (управляющий): «👥 Люди» → инвайты для ст. админов и админов;
   «🔁 Рутина» → шаблоны вида `22:00 Отчёт по кассе`
5. Админ утром жмёт «🟢 Я на смене» — рутинные задачи приходят сами
