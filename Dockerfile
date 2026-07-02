FROM python:3.12-slim

# postgresql-client — для pg_dump (ежедневный бэкап)
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client gzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kyberion_bot ./kyberion_bot

# сюда складываются бэкапы — монтировать volume
RUN mkdir -p /app/backups

CMD ["python", "-m", "kyberion_bot.bot"]
