"""
Telegram-звіт: записи зі статусом 'Опрацьовується'.

Запуск:
    python scripts/tg_report_processing.py

Налаштування:
    TELEGRAM_BOT_TOKEN — токен бота від @BotFather
    TELEGRAM_CHAT_ID   — ID чату/групи, куди надсилати звіт
"""

import html
import os
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# ── Налаштування ──────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_GROUP_ID", "")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN and TELEGRAM_GROUP_ID environment variables are required"
    )

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
STATUS  = "Опрацьовується"

TG_API  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
MAX_LEN = 4096  # ліміт Telegram на одне повідомлення
# ─────────────────────────────────────────────────────────────────────────────


def fetch_records() -> list[dict]:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT history, discharge_department, comment
        FROM   records
        WHERE  discharge_status = ?
        ORDER  BY discharge_department, history
        """,
        (STATUS,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# Максимальна ширина колонок (символів)
MAX_HIST = 12
MAX_DEPT = 20
MAX_COMM = 22


def _col(value: str, width: int) -> str:
    """Обрізає або доповнює рядок до фіксованої ширини."""
    s = value.strip()
    return (s[:width - 1] + "…") if len(s) > width else s.ljust(width)


def build_chunks(records: list[dict]) -> list[str]:
    now   = datetime.now().strftime("%d.%m.%Y %H:%M")
    total = len(records)

    # Динамічна ширина: за фактичними даними, з мінімумом і максимумом
    W_HIST = max(6,  min(MAX_HIST, max(len(r["history"] or "—")                           for r in records)))
    W_DEPT = max(10, min(MAX_DEPT, max(len(r["discharge_department"] or "Без відділення") for r in records)))
    W_COMM = max(8,  min(MAX_COMM, max(len((r["comment"] or "—").strip())                 for r in records)))

    col_header = f"{'Іст. №'.ljust(W_HIST)} │ {'Відділення'.ljust(W_DEPT)} │ Коментар"
    sep        = "─" * (W_HIST + 3 + W_DEPT + 3 + W_COMM)

    # Fix 1: спочатку обрізаємо/вирівнюємо, потім екрануємо HTML
    data_rows = []
    for r in records:
        hist    = html.escape(_col(r["history"] or "—",                           W_HIST))
        dept    = html.escape(_col(r["discharge_department"] or "Без відділення", W_DEPT))
        comment = html.escape(_col((r["comment"] or "—").strip(),                 W_COMM))
        data_rows.append(f"{hist} │ {dept} │ {comment}")

    def make_chunk(rows: list[str], page: str = "") -> str:
        title = f"📋 <b>Опрацьовується · {total} · {now}{page}</b>"
        table = "\n".join([col_header, sep] + rows)
        return f"{title}\n<code>{table}</code>"

    # Спочатку збираємо групи рядків
    raw_chunks: list[list[str]] = []
    current: list[str] = []

    for row in data_rows:
        if len(make_chunk(current + [row])) > MAX_LEN and current:
            raw_chunks.append(current)
            current = [row]
        else:
            current.append(row)

    if current:
        raw_chunks.append(current)

    # Fix 3: додаємо індикатор сторінки якщо повідомлень > 1
    n = len(raw_chunks)
    if n == 1:
        return [make_chunk(raw_chunks[0])]
    return [make_chunk(rows, f" · {i + 1}/{n}") for i, rows in enumerate(raw_chunks)]


def _post(text: str) -> None:
    resp = requests.post(
        TG_API,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    if not resp.ok:
        print("Telegram error:", resp.text)
    resp.raise_for_status()


def main() -> None:
    records = fetch_records()

    if not records:
        _post(
            f"✅ Записів зі статусом «{STATUS}» немає.\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    else:
        for chunk in build_chunks(records):
            _post(chunk)

    print(f"Звіт надіслано ({len(records)} записів).")


if __name__ == "__main__":
    main()
