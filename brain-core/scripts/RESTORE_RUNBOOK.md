# Runbook восстановления после падения VPS

Проверь этот документ хотя бы раз вручную на тестовом VPS — runbook,
который никогда не тестировался, с большой вероятностью не сработает
в реальной аварии.

## 1. Поднять новый VPS

Следуй `brain-v2/scripts/setup_vps.sh` для установки Docker.

## 2. Восстановить Postgres

```bash
gunzip -c postgres_<TIMESTAMP>.sql.gz | psql -h localhost -U <user> -d brain
```

## 3. Восстановить Neo4j

```bash
# Скопировать дамп в новый контейнер
docker cp neo4j_<TIMESTAMP>.dump brain_neo4j:/data/dumps/neo4j.dump
docker exec brain_neo4j neo4j-admin database load neo4j --from-path=/data/dumps --overwrite-destination=true
```

## 4. Поднять стек

```bash
cd brain-v2/docker && docker compose up -d
```

## 5. Проверить целостность

- [ ] Graphiti API отвечает: `curl http://localhost:8000/healthcheck`
- [ ] Postgres содержит ожидаемое число записей:
      `SELECT count(*) FROM freelance.jobs;` — сверить с последним
      известным значением до аварии
- [ ] `brain.pending_decisions` не потерял записи со статусом `pending`
      (это самое критичное — незавершённые решения не должны потеряться)

## 6. Восстановить переменные окружения

`.env` файлы НЕ входят в бэкап БД — храни их отдельно (например, в
менеджере паролей), иначе после восстановления БД система всё равно
не заработает без ключей API.

## 7. Обновить DNS/доступ, если IP сменился

Если новый VPS имеет другой IP — обнови все места, где он захардкожен
(n8n webhooks, конфиги подсистем).
