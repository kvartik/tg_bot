# Деплой Kyberion Task Bot

Бот запускается в Docker: один контейнер с приложением (основной бот + owner-бот +
планировщик) и один с Postgres. Нужен любой Linux-сервер (VPS) с Docker. Ниже —
пошагово «с нуля до работающего бота».

---

## Ссылки на ботов

| Бот | Для кого | Ссылка |
|---|---|---|
| Основной (задачи, смены, рутина) | вся команда | https://t.me/testcopybotpoly_bot |
| Owner-бот (клубы, управляющие, статистика) | только владелец | https://t.me/forcratepostincyberionbot |

> ⚠️ Сейчас в `.env` вписаны токены двух «технических» ботов со старыми именами
> (`сopycustombot`, «Бот для публикации постов»). Перед запуском в бой стоит либо
> **переименовать** их в [@BotFather](https://t.me/BotFather) (`/setname`, `/setuserpic`,
> `/setdescription`), либо **создать новые** бренд-боты и подставить их токены в `.env`
> (`BOT_TOKEN` и `OWNER_BOT_TOKEN`). После смены токенов ссылки выше тоже изменятся.

---

## Что понадобится

- Сервер (VPS) с Ubuntu 22.04+ или Debian 12 — хватит самого дешёвого (1 vCPU, 1 ГБ RAM).
- Доступ по SSH (root или пользователь с sudo).
- Два токена ботов от [@BotFather](https://t.me/BotFather) и ваш Telegram ID
  (узнать у [@userinfobot](https://t.me/userinfobot)).

Хостинг подойдёт любой: Hetzner, DigitalOcean, Timeweb, любой украинский/европейский
VPS-провайдер. Домен и белый IP **не нужны** — бот сам ходит в Telegram (long polling).

---

## Шаг 1. Установить Docker на сервере

Подключитесь по SSH и выполните:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # чтобы docker работал без sudo
# перелогиньтесь (exit и снова ssh), чтобы группа применилась
```

Проверка:

```bash
docker --version
docker compose version
```

## Шаг 2. Загрузить проект на сервер

Вариант А — через git (если проект в репозитории):

```bash
git clone <ваш-репозиторий> kyberion && cd kyberion
```

Вариант Б — скопировать папку с локального компьютера (выполнять **у себя**, не на сервере):

```bash
# .venv и backups не копируем
rsync -av --exclude='.venv' --exclude='backups' --exclude='__pycache__' \
  ./TG/ user@SERVER_IP:~/kyberion/
```

## Шаг 3. Настроить `.env`

На сервере в папке проекта:

```bash
cp .env.example .env
nano .env
```

Заполните:

```ini
BOT_TOKEN=<токен основного бота>
OWNER_BOT_TOKEN=<токен owner-бота>
OWNER_TG_ID=<ваш Telegram ID>
POSTGRES_PASSWORD=<придумайте надёжный пароль>
TZ=Europe/Kyiv
ROUTINE_DEADLINE_MINUTES=60
OVERDUE_REMIND_MINUTES=30
```

> `DATABASE_URL` в docker-compose собирается автоматически из `POSTGRES_PASSWORD` —
> вручную его указывать не нужно. Файл `.env` в git не попадает (он в `.gitignore`).

## Шаг 4. Запустить

```bash
docker compose up -d --build
```

Поднимутся два контейнера: `db` (Postgres 16) и `bot`. Таблицы БД создаются
автоматически при первом старте.

## Шаг 5. Проверить, что всё работает

```bash
docker compose ps          # оба контейнера должны быть Up
docker compose logs -f bot # смотреть логи бота (Ctrl+C — выйти)
```

В логах при успехе не должно быть ошибок токена. Если `OWNER_BOT_TOKEN` не задан,
в логах будет предупреждение и owner-бот просто не запустится (основной — заработает).

Затем в Telegram:
1. Напишите **owner-боту** `/start` — должно открыться «👑 Меню владельца».
2. Создайте клуб, пригласите управляющего (см. [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md)).

---

## Обновление версии

```bash
cd ~/kyberion
git pull                        # или заново скопировать файлы rsync'ом
docker compose up -d --build    # пересоберёт и перезапустит, данные в БД сохранятся
```

## Полезные команды

```bash
docker compose logs -f bot        # логи
docker compose restart bot        # перезапустить только бота
docker compose down               # остановить всё (данные в volume сохраняются)
docker compose up -d              # снова поднять
```

## Данные и бэкапы

- База живёт в Docker-volume `pgdata` — переживает перезапуск и пересборку контейнеров.
- Планировщик каждый день в **04:30** (Europe/Kyiv) делает `pg_dump` в папку `./backups/`
  (сжатый `.sql.gz`), хранит последние **14** копий. Папка примонтирована из хоста —
  бэкапы лежат прямо на сервере в `~/kyberion/backups/`.
- **Ручной бэкап** прямо сейчас:

  ```bash
  docker compose exec db pg_dump --no-owner -U kyberion kyberion | gzip > backup-$(date +%F).sql.gz
  ```

- **Восстановление** из бэкапа:

  ```bash
  gunzip -c backup-2026-07-02.sql.gz | docker compose exec -T db psql -U kyberion -d kyberion
  ```

Периодически скачивайте копии из `./backups/` к себе (например `scp`), чтобы не потерять
данные вместе с сервером.

---

## Частые проблемы

**Бот не отвечает.** `docker compose logs bot` — ищите ошибку. Чаще всего неверный
`BOT_TOKEN`/`OWNER_BOT_TOKEN` или бот не запущен (`docker compose ps`).

**Owner-бот молчит на `/start`.** Проверьте `OWNER_BOT_TOKEN` и что вы пишете именно
с аккаунта, чей ID указан в `OWNER_TG_ID` (бот отвечает только владельцу).

**Два бота отвечают одинаково / путаница.** Убедитесь, что `BOT_TOKEN` и `OWNER_BOT_TOKEN`
— это два **разных** бота, а инвайт-ссылки ведут в основной бот (так и задумано).

**Неправильное время задач.** Проверьте `TZ=Europe/Kyiv` в `.env` и перезапустите
(`docker compose up -d`).
