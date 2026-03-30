"""
Telegram бот-асистент для перегляду медичних записів.

Бот мовчить у групі. В особистих повідомленнях дозволяє обрати відділення
і отримати список записів зі статусами 'Опрацьовується' та 'Порушені вимоги'.
Доступ — лише для членів групи.

Запуск:
    python scripts/tg_bot.py

Env vars:
    TELEGRAM_BOT_TOKEN  — токен бота від @BotFather
    TELEGRAM_GROUP_ID   — ID групи (для перевірки членства), напр. -1001234567890
    DATABASE_URL        — шлях до БД (за замовчуванням sqlite:///data/app.db)
"""

import asyncio
import html
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ── Конфігурація ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GROUP_ID_RAW = os.environ.get("TELEGRAM_GROUP_ID", "")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")
if not GROUP_ID_RAW:
    raise RuntimeError("TELEGRAM_GROUP_ID environment variable is required")

GROUP_ID = int(GROUP_ID_RAW)

_db_url = os.environ.get("DATABASE_URL", "sqlite:///data/app.db")
DB_PATH = Path(
    _db_url.replace("sqlite:////", "/").replace("sqlite:///", "")
)

MAX_LEN = 4096  # ліміт Telegram на одне повідомлення

STATUS_PROCESSING = "Опрацьовується"
STATUS_VIOLATIONS = "Порушені вимоги"
# ─────────────────────────────────────────────────────────────────────────────

router = Router()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_departments() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM departments ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows]


def get_records_for_dept(dept: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT history, discharge_status, treating_physician, comment
            FROM   records
            WHERE  discharge_department = ?
              AND  discharge_status IN (?, ?)
            ORDER  BY
                CASE discharge_status
                    WHEN ? THEN 0
                    ELSE 1
                END,
                history
            """,
            (dept, STATUS_VIOLATIONS, STATUS_PROCESSING, STATUS_VIOLATIONS),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Форматування ──────────────────────────────────────────────────────────────

def _col(value: str | None, width: int) -> str:
    s = (value or "—").strip()
    return (s[: width - 1] + "…") if len(s) > width else s.ljust(width)


def format_dept_report(dept: str, records: list[dict]) -> list[str]:
    """Повертає список повідомлень (пагінація якщо > MAX_LEN)."""
    if not records:
        return [
            f"🏥 <b>{html.escape(dept)}</b>\n\n"
            "Записів зі статусами «Опрацьовується» або «Порушені вимоги» немає."
        ]

    W_HIST = max(6, min(14, max(len(r["history"] or "—") for r in records)))
    W_PHYS = max(8, min(18, max(len(r["treating_physician"] or "—") for r in records)))
    W_COMM = max(8, min(22, max(len((r["comment"] or "—").strip()) for r in records)))

    header = f"{'Іст. №'.ljust(W_HIST)} │ {'Лікар'.ljust(W_PHYS)} │ Коментар"
    sep = "─" * (W_HIST + 3 + W_PHYS + 3 + W_COMM)

    data_rows: list[tuple[str, str]] = []
    for r in records:
        hist = html.escape(_col(r["history"], W_HIST))
        phys = html.escape(_col(r["treating_physician"], W_PHYS))
        comm = html.escape(_col(r["comment"], W_COMM))
        line = f"{hist} │ {phys} │ {comm}"
        data_rows.append((r["discharge_status"], line))

    total = len(records)
    viol_count = sum(1 for s, _ in data_rows if s == STATUS_VIOLATIONS)

    def make_chunk(rows: list[tuple[str, str]], page: str = "") -> str:
        title = (
            f"🏥 <b>{html.escape(dept)}</b> · {total} записів"
            f"{f' · ❌ {viol_count} порушень' if viol_count else ''}"
            f"{page}\n"
        )
        formatted_lines = []
        for status, line in rows:
            if status == STATUS_VIOLATIONS:
                formatted_lines.append(f"❌ <b>{line}</b>")
            else:
                formatted_lines.append(f"⏳ {line}")

        table = "\n".join([header, sep] + formatted_lines)
        return f"{title}<code>{table}</code>"

    # Пагінація
    raw_chunks: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []

    for row in data_rows:
        if len(make_chunk(current + [row])) > MAX_LEN and current:
            raw_chunks.append(current)
            current = [row]
        else:
            current.append(row)
    if current:
        raw_chunks.append(current)

    n = len(raw_chunks)
    if n == 1:
        return [make_chunk(raw_chunks[0])]
    return [make_chunk(rows, f" · {i + 1}/{n}") for i, rows in enumerate(raw_chunks)]


# ── Access control ────────────────────────────────────────────────────────────

async def is_group_member(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(GROUP_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False


# ── Keyboards ─────────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏥 Обрати відділення", callback_data="dept_list")
    return kb


def departments_kb(departments: list[str]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for dept in departments:
        # callback_data обмежений 64 байтами — обрізаємо якщо потрібно
        cb = f"dept:{dept[:50]}"
        kb.button(text=dept, callback_data=cb)
    kb.button(text="◀ Назад", callback_data="main_menu")
    kb.adjust(1)
    return kb


def back_to_depts_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="◀ До відділень", callback_data="dept_list")
    return kb


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message) -> None:
    if not await is_group_member(message.bot, message.from_user.id):
        await message.answer("⛔ Доступ лише для членів групи.")
        return

    await message.answer(
        f"Привіт, {html.escape(message.from_user.first_name)}!\n"
        "Оберіть дію:",
        reply_markup=main_menu_kb().as_markup(),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(query: CallbackQuery) -> None:
    if not await is_group_member(query.bot, query.from_user.id):
        await query.answer("⛔ Немає доступу", show_alert=True)
        return

    await query.message.edit_text(
        "Оберіть дію:",
        reply_markup=main_menu_kb().as_markup(),
    )
    await query.answer()


@router.callback_query(F.data == "dept_list")
async def cb_dept_list(query: CallbackQuery) -> None:
    if not await is_group_member(query.bot, query.from_user.id):
        await query.answer("⛔ Немає доступу", show_alert=True)
        return

    departments = get_departments()
    if not departments:
        await query.answer("Відділень не знайдено.", show_alert=True)
        return

    await query.message.edit_text(
        "Оберіть відділення:",
        reply_markup=departments_kb(departments).as_markup(),
    )
    await query.answer()


@router.callback_query(F.data.startswith("dept:"))
async def cb_dept(query: CallbackQuery) -> None:
    if not await is_group_member(query.bot, query.from_user.id):
        await query.answer("⛔ Немає доступу", show_alert=True)
        return

    dept = query.data[len("dept:"):]
    records = get_records_for_dept(dept)
    chunks = format_dept_report(dept, records)

    # Перше повідомлення — редагуємо поточне
    await query.message.edit_text(
        chunks[0],
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_depts_kb().as_markup() if len(chunks) == 1 else None,
    )

    # Додаткові сторінки — нові повідомлення
    for i, chunk in enumerate(chunks[1:], start=1):
        is_last = i == len(chunks) - 1
        await query.message.answer(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_depts_kb().as_markup() if is_last else None,
        )

    await query.answer()


# Ігнорувати всі повідомлення в групі (не відповідати)
@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def ignore_group(_: Message) -> None:
    return


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=None)
    dp = Dispatcher()
    dp.include_router(router)

    print(f"Bot started. DB: {DB_PATH}. Group ID: {GROUP_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
