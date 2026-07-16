#!/usr/bin/env bash
set -euo pipefail

# Ежедневный бэкап Postgres (дамп) и Neo4j (экспорт), с выгрузкой ВНЕ
# того же VPS — бэкап на том же диске бесполезен при падении сервера.
#
# Настрой BACKUP_REMOTE_PATH на внешнее хранилище (другой VPS, S3-совместимое
# хранилище, что угодно доступное через rclone/scp). Без этого шага
# бэкап существует только в теории.
#
# Рекомендуется в cron: 0 3 * * * /path/to/backup.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-/var/backups/brain}"
BACKUP_REMOTE_PATH="${BACKUP_REMOTE_PATH:-}"  # напр. "myremote:brain-backups/" для rclone

mkdir -p "$LOCAL_BACKUP_DIR"

echo "== Дамп Postgres =="
PG_DUMP_FILE="$LOCAL_BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"
pg_dump -h "${POSTGRES_HOST:-localhost}" -U "${POSTGRES_USER}" "${POSTGRES_DB:-brain}" \
    | gzip > "$PG_DUMP_FILE"
echo "Сохранено: $PG_DUMP_FILE ($(du -h "$PG_DUMP_FILE" | cut -f1))"

echo "== Экспорт Neo4j =="
# NOTE: реальная команда зависит от того, как развёрнут Neo4j (docker exec
# внутрь контейнера или neo4j-admin напрямую). Пример для Docker-варианта
# из brain-v2/docker/docker-compose.yml:
NEO4J_DUMP_FILE="$LOCAL_BACKUP_DIR/neo4j_${TIMESTAMP}.dump"
if docker ps --format '{{.Names}}' | grep -q brain_neo4j; then
    docker exec brain_neo4j neo4j-admin database dump neo4j --to-path=/data/dumps || \
        echo "ВНИМАНИЕ: команда дампа могла измениться в новых версиях Neo4j — сверься с документацией"
    docker cp brain_neo4j:/data/dumps/neo4j.dump "$NEO4J_DUMP_FILE" || true
else
    echo "ВНИМАНИЕ: контейнер brain_neo4j не найден, пропускаю экспорт Neo4j"
fi

if [ -n "$BACKUP_REMOTE_PATH" ]; then
    echo "== Выгрузка на внешнее хранилище =="
    rclone copy "$LOCAL_BACKUP_DIR" "$BACKUP_REMOTE_PATH" --include "*${TIMESTAMP}*"
else
    echo "ВНИМАНИЕ: BACKUP_REMOTE_PATH не задан — бэкап остался только на этом VPS."
    echo "Это НЕ настоящий бэкап, пока не выгружен на отдельное хранилище."
fi

echo "== Очистка старых локальных бэкапов (старше 7 дней) =="
find "$LOCAL_BACKUP_DIR" -type f -mtime +7 -delete

echo "Готово: $TIMESTAMP"
