#!/usr/bin/env bash
set -euo pipefail

# Установка Docker + запуск стека Neo4j/Graphiti на чистом Ubuntu VPS.
# Предполагается, что Postgres/pgvector из Phase 1 уже стоит и работает —
# этот скрипт его не трогает.

echo "== Обновление системы =="
sudo apt-get update -y
sudo apt-get upgrade -y

echo "== Установка Docker (если ещё не установлен) =="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    rm get-docker.sh
    echo "Docker установлен. Может понадобиться перелогиниться, чтобы группа docker применилась."
else
    echo "Docker уже установлен, пропускаем."
fi

echo "== Проверка docker compose =="
docker compose version

echo "== Готово =="
echo "Дальше:"
echo "1. cd docker"
echo "2. cp .env.example .env && nano .env   # заполни ключи и пароль Neo4j"
echo "3. docker compose up -d"
echo "4. curl http://localhost:8000/healthcheck   # проверка Graphiti API"
