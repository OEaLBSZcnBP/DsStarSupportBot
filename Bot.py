import os
import asyncio
import re
import sqlite3
import aiohttp
import math
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ChatMemberStatus

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ ОШИБКА: токен не найден. Создай .env или задай BOT_TOKEN.")
    exit()

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============ БАЗА ДАННЫХ ============
db = sqlite3.connect("moderation.db")
db.execute("CREATE TABLE IF NOT EXISTS warns (user_id INTEGER, chat_id INTEGER, count INTEGER, last_warn DATETIME, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS mutes (user_id INTEGER, chat_id INTEGER, until DATETIME, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER, chat_id INTEGER, until DATETIME, PRIMARY KEY(user_id, chat_id))")
db.commit()


# ============ ПАРСЕР ВРЕМЕНИ ============
def parse_time(text):
    """Парсит '5 дней', '7d', '1h', '30m' → timedelta"""
    if not text:
        return None
    m = re.match(r"^(\d+)\s*(секунд|сек|second|sec|s|минут|мин|минуты|min|m|час|часа|часов|hour|h|дней|день|дня|day|d|недел|неделя|недели|week|w|месяц|month|mo|год|года|лет|year|y)?$", text.strip().lower())
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2) or "h"
    if unit in ("секунд", "сек", "second", "sec", "s"):
        return timedelta(seconds=val)
    if unit in ("минут", "мин", "минуты", "min", "m"):
        return timedelta(minutes=val)
    if unit in ("час", "часа", "часов", "hour", "h"):
        return timedelta(hours=val)
    if unit in ("дней", "день", "дня", "day", "d"):
        return timedelta(days=val)
    if unit in ("недел", "неделя", "недели", "week", "w"):
        return timedelta(weeks=val)
    if unit in ("месяц", "month", "mo"):
        return timedelta(days=val * 30)
    if unit in ("год", "года", "лет", "year", "y"):
        return timedelta(days=val * 365)
    return None


def format_td(td):
    """timedelta → '5 дней' """
    sec = int(td.total_seconds())
    if sec < 60:
        return f"{sec} сек"
    if sec < 3600:
        return f"{sec // 60} мин"
    if sec < 86400:
        return f"{sec // 3600} час"
    if sec < 2592000:
        return f"{sec // 86400} дней"
    return f"{sec // 2592000} мес"


# ============ ПАРСЕР ЦЕЛИ ============
async def get_target(m: types.Message):
    """Получает цель: реплай, юзернейм, айди"""
    if m.reply_to_message:
        return m.reply_to_message.from_user
    parts = m.text.split()
    for p in parts[1:]:
        if p.startswith("@"):
            try:
                u = await bot.get_chat(p)
                return u
            except:
                pass
        if p.isdigit():
            try:
                u = await bot.get_chat(int(p))
                return u
            except:
                pass
    return None


# ============ /start ============
@dp.message(Command("start"))
async def start(m: types.Message):
    user = m.from_user
    name = user.first_name or user.username or "друг"
    await m.answer(
        f"👋 Доброго времени суток, {name}!\n\n"
        f"🤖 Я бот-помощник для специальных чатов.\n\n"
        f"💡 У меня есть Inline mode — напишите в ЛС или в своем чате "
        f"@DsStarSupportBot и тогда вы сможете его использовать."
    )


# ============ /commands ============
@dp.message(Command("commands"))
async def commands(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Семейство Звёздных", callback_data="cmds_stars")],
        [InlineKeyboardButton(text="🛡 Саппорт", callback_data="cmds_support")]
    ])
    await m.answer("📋 Список команд какого бота вас интересует?", reply_markup=kb)


@dp.callback_query(F.data.startswith("cmds_"))
async def cmds_cb(c: types.CallbackQuery):
    if c.data == "cmds_stars":
        await c.message.answer("https://telegra.ph/Komandy-zvezdnogo-semejstva-07-15")
    else:
        await c.message.answer("https://telegra.ph/Komandy-StarSupportBot-07-15")
    await c.answer()


# ============ /ban ============
@dp.message(Command("ban", "бан"))
async def ban(m: types.Message):
    if m.chat.type == "private":
        return await m.answer("❌ Команда работает только в группах")
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /ban 5 дней @user или реплай")

    time_text = None
    for p in m.text.split()[1:]:
        if not p.startswith("@") and not p.isdigit():
            time_text = p + " " + (m.text.split()[m.text.split().index(p) + 1] if m.text.split().index(p) + 1 < len(m.text.split()) else "")
            break

    td = parse_time(time_text) if time_text else None
    until = datetime.now() + td if td else None

    try:
        await bot.ban_chat_member(m.chat.id, target.id, until_date=until)
    except Exception as e:
        return await m.answer(f"❌ Не удалось забанить: {e}")

    db.execute("INSERT OR REPLACE INTO bans VALUES (?, ?, ?)", (target.id, m.chat.id, until))
    db.commit()

    period = format_td(td) if td else "навсегда"
    name = f"@{target.username}" if target.username else target.first_name
    reason = m.text.split(None, 1)[1].split(None, 1)[1] if len(m.text.split(None, 1)) > 1 and len(m.text.split(None, 1)[1].split()) > 1 else "не указана"
    await m.answer(f"🔴 {name} забанен на {period}.\n📝 Причина: {reason}")


# ============ /unban ============
@dp.message(Command("unban", "анбан"))
async def unban(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /unban @user или реплай")

    try:
        await bot.unban_chat_member(m.chat.id, target.id)
        db.execute("DELETE FROM bans WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        await m.answer(f"✅ {name} разбанен")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


# ============ /mute ============
@dp.message(Command("mute", "мут"))
async def mute(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /mute 7 дней @user")

    parts = m.text.split()
    time_text = None
    for i, p in enumerate(parts[1:]):
        if p.isdigit() and i + 1 < len(parts) - 1:
            time_text = f"{p} {parts[i + 2]}"
            break

    td = parse_time(time_text) if time_text else timedelta(hours=1)
    until = datetime.now() + td

    try:
        await bot.restrict_chat_member(
            m.chat.id, target.id,
            types.ChatPermissions(),
            until_date=until
        )
        db.execute("INSERT OR REPLACE INTO mutes VALUES (?, ?, ?)", (target.id, m.chat.id, until))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        reason = "не указана"
        args = m.text.split(None, 1)
        if len(args) > 1:
            words = args[1].split()
            if len(words) > 1 and not words[0].isdigit():
                reason = " ".join(words[1:])
        await m.answer(f"❗️ {name} лишился права слова на {format_td(td)}.\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


# ============ /unmute ============
@dp.message(Command("unmute", "анмут"))
async def unmute(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /unmute @user")

    try:
        await bot.restrict_chat_member(
            m.chat.id, target.id,
            types.ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        db.execute("DELETE FROM mutes WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        await m.answer(f"✅ {name} срок молчания окончен, но лучше следите за языком..")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


# ============ /warn ============
@dp.message(Command("warn", "варн"))
async def warn(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /warn @user или реплай")

    cur = db.execute("SELECT count, last_warn FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    count = (row[0] if row else 0) + 1
    now = datetime.now()
    db.execute("INSERT OR REPLACE INTO warns VALUES (?, ?, ?, ?)", (target.id, m.chat.id, count, now))
    db.commit()

    name = f"@{target.username}" if target.username else target.first_name
    reason = m.text.split(None, 1)[1].split(None, 1)[1] if len(m.text.split(None, 1)) > 1 and len(m.text.split(None, 1)[1].split()) > 1 else "не указана"
    await m.answer(
        f"❗️ {name} получает 1 предупреждение.\n"
        f"📊 {count}/5\n"
        f"⏰ Снимется через неделю\n"
        f"📝 Причина: {reason}"
    )

    if count >= 5:
        try:
            await bot.ban_chat_member(m.chat.id, target.id, until_date=datetime.now() + timedelta(days=30))
            await m.answer(f"🔴 {name} получил бан на 1 месяц (5/5 варнов)")
            db.execute("DELETE FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
            db.commit()
        except:
            pass


# ============ /takewarn ============
@dp.message(Command("takewarn", "анварн"))
async def takewarn(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /takewarn @user")

    cur = db.execute("SELECT count FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    if not row or row[0] <= 0:
        return await m.answer("❌ У него нет варнов")
    new_count = row[0] - 1
    db.execute("UPDATE warns SET count=? WHERE user_id=? AND chat_id=?", (new_count, target.id, m.chat.id))
    db.commit()

    name = f"@{target.username}" if target.username else target.first_name
    await m.answer(f"✅ Варн с {name} снят. Осталось: {new_count}/5")


# ============ /wwarns ============
@dp.message(Command("wwarns", "варны"))
async def wwarns(m: types.Message):
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /wwarns @user")

    cur = db.execute("SELECT count, last_warn FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    name = f"@{target.username}" if target.username else target.first_name

    if not row or row[0] == 0:
        return await m.answer(f"📋 У {name} нет предупреждений")

    days_left = 7 - (datetime.now() - datetime.fromisoformat(row[1])).days
    await m.answer(
        f"📋 Варны {name}:\n"
        f"Количество: {row[0]}/5\n"
        f"Последний: {row[1][:10]}\n"
        f"Снимется через: {max(0, days_left)} дн."
    )


# ============ /kick ============
@dp.message(Command("kick", "кик"))
async def kick(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /kick @user")

    try:
        await bot.ban_chat_member(m.chat.id, target.id, until_date=datetime.now() + timedelta(seconds=30))
        await bot.unban_chat_member(m.chat.id, target.id)
        name = f"@{target.username}" if target.username else target.first_name
        reason = m.text.split(None, 1)[1].split(None, 1)[1] if len(m.text.split(None, 1)) > 1 and len(m.text.split(None, 1)[1].split()) > 1 else "не указана"
        await m.answer(f"✅ Пользователь {name} исключён.\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


# ============ /report ============
@dp.message(Command("report", "репорт"))
async def report(m: types.Message):
    if not m.reply_to_message:
        return await m.answer("❌ Репорт только через реплай!")
    violator = m.reply_to_message.from_user
    sender = m.from_user
    chat_id = m.chat.id
    msg_id = m.reply_to_message.message_id
    link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{msg_id}"

    violator_name = f"@{violator.username}" if violator.username else violator.first_name
    sender_name = f"@{sender.username}" if sender.username else sender.first_name

    reason = m.text.split(None, 1)[1] if len(m.text.split(None, 1)) > 1 else "не указана"

    await m.answer(f"✅ Жалоба на {violator_name} отправлена")

    admins = await bot.get_chat_administrators(chat_id)
    for adm in admins:
        if adm.user.id == bot.id:
            continue
        try:
            await bot.send_message(
                adm.user.id,
                f"❗️ОБНАРУЖЕН НАРУШИТЕЛЬ❗️\n\n"
                f"Нарушитель: {violator_name}\n"
                f"Отправитель: {sender_name}\n"
                f"Сообщение: {link}\n"
                f"Причина: {reason}"
            )
        except:
            pass


# ============ /calculator ============
@dp.message(Command("calculator", "calc"))
async def calc(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("/calculator 2+2*2")
    expr = args[1]
    expr = expr.replace(" ", "")
    expr = expr.replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", ".")
    expr = expr.replace("√(", "math.sqrt(").replace("sqrt(", "math.sqrt(")
    expr = expr.replace("^", "**")
    expr = expr.replace("π", "math.pi")
    try:
        res = eval(expr, {"math": math, "__builtins__": {}})
        await m.answer(f"🧮 {args[1]} = {res}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)[:80]}")


# ============ /meta ============
@dp.message(Command("meta", "мета"))
async def meta(m: types.Message):
    await m.answer(
        "⚠ Пожалуйста, не задавайте мета-вопросов в чате!\n\n"
        "❓Мета-вопрос — это вопрос, который подразумевает другие вопросы, например:\n"
        "• Можно ли задать вопрос?\n"
        "• Есть, кто разбирается в ...?\n"
        "• Кто может помочь?\n\n"
        "💬 Они тратят время! И ваше, и других людей, которые пытаются вам помочь. Переходите сразу к делу."
    )


# ============ /offtop ============
@dp.message(Command("offtop", "оффтоп"))
async def offtop(m: types.Message):
    await m.answer(
        "⚠️ Внимание! В этой беседе запрещён оффтоп.\n"
        "Если вы хотите поболтать или обсудить что-то, то переходите в тему для этого.\n\n"
        "❓ Оффтоп — сообщения не по теме чата. Предназначение этой темы находится в закрепленном сообщении.\n\n"
        "❌ Если вы проигнорируете это сообщение, то модераторы в полном праве могут выдать вам наказание!"
    )


# ============ /search ============
@dp.message(Command("search", "поиск"))
async def search(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("/search Запрос")
    from urllib.parse import quote
    url = f"https://yandex.ru/search/?text={quote(args[1])}"
    await m.answer(f"🔍 Вот ссылка на Яндекс:\n{url}")


# ============ /about ============
@dp.message(Command("about", "about"))
async def about(m: types.Message):
    await m.answer(
        "ℹ️ О боте:\n\n"
        "Язык программирования: Python.\n"
        "Библиотека: Aiogram."
    )


# ============ /catalog ============
@dp.message(Command("catalog", "каталог"))
async def catalog(m: types.Message):
    await m.answer(
        "📂 Специальные чаты:\n\n"
        "⭐ StarHub [Официальный чат]:\n"
        "https://t.me/DeliciousStarHub\n\n"
        "🍪 Пряники:\n"
        "https://t.me/chatvaznihludey\n\n"
        "🔪 Мафия:\n"
        "https://t.me/DarkMafiaChat11"
    )


# ============ /help ============
@dp.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.answer(
        "📋 Все команды:\n\n"
        "• /start — приветствие\n"
        "• /ban 5 дней @user — бан\n"
        "• /unban @user — разбан\n"
        "• /mute 7 дней @user — мут\n"
        "• /unmute @user — снять мут\n"
        "• /warn @user — варн\n"
        "• /takewarn @user — снять варн\n"
        "• /wwarns @user — список варнов\n"
        "• /kick @user — кик\n"
        "• /report — жалоба (реплай)\n"
        "• /calculator 2+2 — калькулятор\n"
        "• /meta — про мета-вопросы\n"
        "• /offtop — про оффтоп\n"
        "• /search запрос — Яндекс\n"
        "• /commands — каталог команд\n"
        "• /about — о боте\n"
        "• /catalog — каталог чатов"
    )


# ============ ЗАПУСК ============
async def main():
    print("✅ Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
