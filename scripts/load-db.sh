#!/usr/bin/env bash
#
# load-db.sh — залити .db-файл з хоста у named volume контейнера і привести схему до head.
#
# Контейнер читає БД з named volume (не з ./data на хості), тому проста заміна файлу
# на хості не діє. Скрипт копіює файл усередину через `docker cp`, виставляє власника
# й чистить залишкові WAL/SHM ДО старту, а схему до head доводить штатний `flask db upgrade`
# у entrypoint (тобто справжні міграції, без «брехливого» stamp head).
#
# Використання:
#   bash scripts/load-db.sh [шлях_до_файлу.db]
#   bash scripts/load-db.sh ./data/app.db            # за замовчуванням
#   CONTAINER=flask_app SERVICES="web tg-bot" bash scripts/load-db.sh /шлях/до/dump.db
#
# Змінні оточення (зі значеннями за замовчуванням під цей проєкт):
#   CONTAINER  — ім'я app-контейнера            (flask_app)
#   SERVICE    — ім'я compose-сервісу для run    (web)
#   DBPATH     — шлях до БД усередині контейнера (/app/data/app.db)
#   SERVICES   — compose-сервіси для stop/start  (web tg-bot)
#   DBUSER     — власник файлу БД у контейнері   (appuser:appgroup)
#
set -euo pipefail

# Git Bash/MSYS на Windows інакше переписує абсолютні шляхи (/app/...) у Windows-шляхи
# перед передачею в docker. На Linux ці змінні нешкідливі (ігноруються).
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

SRC="${1:-./data/app.db}"
CONTAINER="${CONTAINER:-flask_app}"
SERVICE="${SERVICE:-web}"
DBPATH="${DBPATH:-/app/data/app.db}"
SERVICES="${SERVICES:-web tg-bot}"
DBUSER="${DBUSER:-appuser:appgroup}"

if [ ! -f "$SRC" ]; then
    echo "ПОМИЛКА: файл-джерело не знайдено: $SRC" >&2
    exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"

echo "==> Джерело:     $SRC"
echo "==> Контейнер:   $CONTAINER  (БД: $DBPATH)"
echo "==> Сервіси:     $SERVICES"
echo

echo "[1/6] Страховий бекап поточної БД у volume (поки контейнер запущено)..."
docker exec "$CONTAINER" flask backup-db -o "/app/data/pre_load_$TS.db" || \
    echo "    (бекап пропущено — контейнер міг бути зупинений)"

echo "[2/6] Зупиняю сервіси (зняти SQLite-локи; чистий stop обнуляє WAL)..."
docker compose stop $SERVICES

echo "[3/6] Копіюю файл у контейнер ($DBPATH)..."
docker cp "$SRC" "$CONTAINER:$DBPATH"

echo "[4/6] Виставляю власника й чищу залишкові WAL/SHM (ДО старту, через one-off root-контейнер)..."
# Запускаємо разовий контейнер того ж образу як root з тим самим volume, перевизначивши entrypoint.
docker compose run --rm --no-deps --user 0 --entrypoint sh "$SERVICE" -c \
    "chown $DBUSER '$DBPATH' && rm -f '${DBPATH}-wal' '${DBPATH}-shm'"

echo "[5/6] Запускаю сервіси — entrypoint сам застосує 'flask db upgrade' до head..."
docker compose up -d $SERVICES

echo "[6/6] Перевірка..."
echo "==> Поточна ревізія схеми (має бути '(head)'):"
CURRENT="$(docker exec "$CONTAINER" flask db current 2>&1 | grep -iv 'warn\|in-memory' | tail -1 || true)"
echo "    $CURRENT"
if ! printf '%s' "$CURRENT" | grep -q '(head)'; then
    echo "    !! УВАГА: схема НЕ на head. Ймовірно дамп має дрейф схеми (фізична структура не"
    echo "       збігається зі своїм alembic-штампом). Доведи вручну, наприклад:"
    echo "         docker exec $CONTAINER flask db stamp <ревізія_що_відповідає_фактичній_схемі>"
    echo "         docker exec $CONTAINER flask db upgrade"
fi
echo "==> Лічильники в живій базі:"
docker exec "$CONTAINER" python -c "import sqlite3; c=sqlite3.connect('$DBPATH'); t=[r[0] for r in c.execute(\"select name from sqlite_master where type='table'\")]; print('  nszu_corrections =', c.execute('select count(*) from nszu_corrections').fetchone()[0] if 'nszu_corrections' in t else 'НЕМАЄ ТАБЛИЦІ'); print('  records          =', c.execute('select count(*) from records').fetchone()[0] if 'records' in t else 'НЕМАЄ ТАБЛИЦІ'); print('  ambulatory_records present:', 'ambulatory_records' in t)"
