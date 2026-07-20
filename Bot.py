import os
import asyncio
import re
import sqlite3
import math
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
import aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ ОШИБКА: токен не найден. Создай .env или задай BOT_TOKEN.")
    exit()

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = sqlite3.connect("moderation.db")
db.execute("CREATE TABLE IF NOT EXISTS warns (user_id INTEGER, chat_id INTEGER, count INTEGER, last_warn TEXT, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS mutes (user_id INTEGER, chat_id INTEGER, until TEXT, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER, chat_id INTEGER, until TEXT, PRIMARY KEY(user_id, chat_id))")
db.commit()


def parse_time(text):
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


async def get_target(m):
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


@dp.message(Command("id"))
async def get_id(m: types.Message):
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /id @user или реплай")
    await m.answer(f"🆔 ID пользователя: <code>{target.id}</code>", parse_mode="HTML")


@dp.message(Command("ban", "бан"))
async def ban(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /ban 5 дней @user или реплай")
    parts = m.text.split()
    time_text = None
    for p in parts[1:]:
        if not p.startswith("@") and not p.isdigit() and p != parts[1]:
            time_text = p
            break
    td = parse_time(time_text) if time_text else None
    until = datetime.now() + td if td else None
    try:
        await bot.ban_chat_member(m.chat.id, target.id, until_date=until)
        db.execute("INSERT OR REPLACE INTO bans VALUES (?, ?, ?)", (target.id, m.chat.id, until.isoformat() if until else None))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        period = format_td(td) if td else "навсегда"
        reason = "не указана"
        args = m.text.split(None, 1)
        if len(args) > 1:
            words = args[1].split()
            for w in words:
                if w.isdigit() or parse_time(w):
                    idx = words.index(w)
                    reason = " ".join(words[idx+1:]) if idx + 1 < len(words) else "не указана"
                    break
        await m.answer(f"🔴 {name} забанен на {period}.\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("unban", "анбан"))
async def unban(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /unban @user")
    try:
        await bot.unban_chat_member(m.chat.id, target.id)
        db.execute("DELETE FROM bans WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        await m.answer(f"✅ {name} разбанен")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("mute", "мут"))
async def mute(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /mute 7 дней @user")
    parts = m.text.split()
    time_text = None
    for i in range(1, len(parts) - 1):
        if parts[i].isdigit():
            time_text = f"{parts[i]} {parts[i+1]}"
            break
    td = parse_time(time_text) if time_text else timedelta(hours=1)
    until = datetime.now() + td
    try:
        await bot.restrict_chat_member(m.chat.id, target.id, types.ChatPermissions(), until_date=until)
        db.execute("INSERT OR REPLACE INTO mutes VALUES (?, ?, ?)", (target.id, m.chat.id, until.isoformat()))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        reason = "не указана"
        args = m.text.split(None, 1)
        if len(args) > 1:
            words = args[1].split()
            for w in words:
                if w.isdigit() or parse_time(w):
                    idx = words.index(w)
                    reason = " ".join(words[idx+1:]) if idx + 1 < len(words) else "не указана"
                    break
        await m.answer(f"❗️ {name} лишился права слова на {format_td(td)}.\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("unmute", "анмут"))
async def unmute(m: types.Message):
    if m.chat.type == "private":
        return
    target = await get_target(m)
    if not target:
        return await m.answer("❌ Укажите: /unmute @user")
    try:
        await bot.restrict_chat_member(m.chat.id, target.id, types.ChatPermissions(
            can_send_messages=True, 
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True, 
            can_send_other_messages=True,
            can_add_web_page_previews=True
        ))
        db.execute("DELETE FROM mutes WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        name = f"@{target.username}" if target.username else target.first_name
        await m.answer(f"✅ {name} срок молчания окончен, но лучше следите за языком..")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


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
    now = datetime.now().isoformat()
    db.execute("INSERT OR REPLACE INTO warns VALUES (?, ?, ?, ?)", (target.id, m.chat.id, count, now))
    db.commit()
    name = f"@{target.username}" if target.username else target.first_name
    reason = "не указана"
    args = m.text.split(None, 1)
    if len(args) > 1:
        words = args[1].split()
        for w in words:
            if w.startswith("@") or w.isdigit():
                idx = words.index(w)
                reason = " ".join(words[idx+1:]) if idx + 1 < len(words) else "не указана"
                break
    await m.answer(f"❗️ {name} получает 1 предупреждение.\n📊 {count}/5\n⏰ Снимется через неделю\n📝 Причина: {reason}")
    if count >= 5:
        try:
            await bot.ban_chat_member(m.chat.id, target.id, until_date=datetime.now() + timedelta(days=30))
            await m.answer(f"🔴 {name} получил бан на 1 месяц (5/5 варнов)")
            db.execute("DELETE FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
            db.commit()
        except:
            pass


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
    await m.answer(f"📋 Варны {name}:\nКоличество: {row[0]}/5\nПоследний: {row[1][:10]}\nСнимется через: {max(0, days_left)} дн.")


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
        reason = "не указана"
        args = m.text.split(None, 1)
        if len(args) > 1:
            words = args[1].split()
            for w in words:
                if w.startswith("@") or w.isdigit():
                    idx = words.index(w)
                    reason = " ".join(words[idx+1:]) if idx + 1 < len(words) else "не указана"
                    break
        await m.answer(f"✅ Пользователь {name} исключён.\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


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
            await bot.send_message(adm.user.id,
                f"❗️ОБНАРУЖЕН НАРУШИТЕЛЬ❗️\n\nНарушитель: {violator_name}\nОтправитель: {sender_name}\nСообщение: {link}\nПричина: {reason}")
        except:
            pass


@dp.message(Command("calculator", "calc"))
async def calc(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("❌ /calculator 2+2*2")
    expr = args[1].replace(" ", "").replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", ".")
    expr = expr.replace("√(", "math.sqrt(").replace("sqrt(", "math.sqrt(").replace("^", "**").replace("π", "math.pi")
    try:
        res = eval(expr, {"math": math, "builtins": {}})
        await m.answer(f"🧮 {args[1]} = {res}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {str(e)[:80]}")


@dp.message(Command("Currency", "currency", "курс", "курсы"))
async def course(m: types.Message):
    t = "💹 КУРСЫ В ДОЛЛАРАХ (USD):\n\n📊 Крипта:\n"
    try:
        async with aiohttp.ClientSession() as s:
            url = "https://api.coinpaprika.com/v1/tickers"
            async with s.get(url, timeout=10) as r:
                d = await r.json()
                ids = {
                    "btc-bitcoin": "BTC", "eth-ethereum": "ETH", "sol-solana": "SOL",
                    "toncoin-ton": "TON", "doge-dogecoin": "DOGE", "xrp-xrp": "XRP",
                    "bnb-binance-coin": "BNB", "ada-cardano": "ADA", "trx-tron": "TRX",
                    "matic-polygon": "MATIC", "ltc-litecoin": "LTC", "avax-avalanche": "AVAX",
                    "dot-polkadot": "DOT", "link-chainlink": "LINK", "near-near-protocol": "NEAR",
                    "atom-cosmos": "ATOM"
                }
                for x in d:
                    if x["id"] in ids:
                        p = x["quotes"]["USD"]["price"]
                        t += f"{ids[x['id']]}: ${p:,.4f}\n"
    except:
        t += "⚠️ крипта недоступна\n"

    t += "\n💵 Фиат (1 единица = $):\n"
    try:
        async with aiohttp.ClientSession() as s:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            async with s.get(url, timeout=10) as r:
                d = await r.json()
                rates = d.get("rates", {})
                for code, name in [("RUB", "₽ Рубль"), ("EUR", "€ Евро"), ("CNY", "¥ Юань"), ("GBP", "£ Фунт"), ("JPY", "¥ Йена"), ("KZT", "₸ Тенге"), ("UAH", "₴ Гривна"), ("TRY", "₺ Лира")]:
                    if code in rates:
                        t += f"1 {code} = ${rates[code]:.4f}\n"
    except:
        t += "⚠️ фиат недоступен"

    await m.answer(t)


@dp.message(Command("meta", "мета"))
async def meta(m: types.Message):
    await m.answer(
        "⚠ Пожалуйста, не задавайте мета-вопросов в чате!\n\n"
        "❓Мета-вопрос — это вопрос, который подразумевает другие вопросы, например:\n"
        "• Можно ли задать вопрос?\n"
        "• Есть, кто разбирается в ...?\n"
        "• Кто может помочь?\n\n"
        "💬 Они тратят время! И ваше, и других людей, которые пытаются вам помочь. Переходите сразу к делу.")


@dp.message(Command("offtop", "оффтоп"))
async def offtop(m: types.Message):
    await m.answer(
        "⚠️ Внимание! В этой беседе запрещён оффтоп.\n"
        "Если вы хотите поболтать или обсудить что-то, то переходите в тему для этого.\n\n"
        "❓ Оффтоп — сообщения не по теме чата. Предназначение этой темы находится в закрепленном сообщении.\n\n"
        "❌ Если вы проигнорируете это сообщение, то модераторы в полном праве могут выдать вам наказание!")


@dp.message(Command("search", "поиск"))
async def search(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("❌ /search Запрос")
    from urllib.parse import quote
    url = f"https://yandex.ru/search/?text={quote(args[1])}"
    await m.answer(f"🔍 {url}")


@dp.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.answer(
        "📋 Команды:\n\n"
        "• /start — приветствие\n"
        "• /id @user — получить ID\n"
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
        "• /Currency — курсы валют и крипты\n"
        "• /meta — про мета-вопросы\n"
        "• /offtop — про оффтоп\n"
        "• /search запрос — Яндекс\n"
        "• /commands — каталог команд\n\n"
        "💡 Инлайн: @DsStarSupportBot каталог / о ботах / сделать чат спец.")


@dp.inline_query()
async def inline_handler(q: types.InlineQuery):
    query = q.query.strip().lower()
    results = []

    if query in ["о ботах", "about bot", "о ботах.", "о"]:
        results.append(
            InlineQueryResultArticle(
                id="about-1",
                title="🤖 О ботах",
                description="Инфо о ботах",
                input_message_content=InputTextMessageContent(
                    message_text="ℹ️ О ботах:\n\nЯзык программирования: Python.\nБиблиотека: Aiogram."
                )
            )
        )

    if query in ["каталог", "catalog", "чаты", "chats"]:
        results.append(
            InlineQueryResultArticle(
                id="catalog-1",
                title="📂 Каталог",
                description="Специальные чаты",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "📂 Специальные чаты:\n\n"
                        "⭐ StarHub [Официальный чат]:\n"
                        "https://t.me/DeliciousStarHub\n\n"
                        "🍪 Пряники:\n"
                        "https://t.me/chatvaznihludey\n\n"
                        "🔪 Мафия:\n"
                        "https://t.me/DarkMafiaChat11"
                    )
                )
            )
        )

    if query in ["сделать свой чат специальным", "спец чат", "спецчат", "сделать спец", "сделать чат специальным", "сделать чат специальным", "специальный чат"]:
        results.append(
            InlineQueryResultArticle(
                id="specchat-1",
                title="✨ Сделать свой чат специальным",
                description="Сделать мой чат специальным",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "✨ Чтобы сделать свой чат специальным нужно:\n\n"
                        "1) Зайти в чат t.me/DeliciousStarHub.\n\n"
                        "2) Зайти в тему «Техническая поддержка» и написать сообщение с #спец чат.\n"
                        "В сообщение должна быть подробная информация о чате, о чем он, и тому подобная информация.\n\n"
                        "3) Ждать ответ админа/владельца, если чат по описанию подойдет вас попросят дать ссылку на чат в секретном сообщении @PPBBOT, чтобы убедиться, что вся информация правдива.\n"
                        "Если ваш чат подойдет, вы сможете добавить саппорта себе в чат."
                    )
                )
            )
        )

    if not results:
        results = [
            InlineQueryResultArticle(
                id="about-default",
                title="🤖 О ботах",
                description="Инфо о ботах",
                input_message_content=InputTextMessageContent(
                    message_text="ℹ️ О ботах:\n\nЯзык программирования: Python.\nБиблиотека: Aiogram.\nКодер: @Luxscer"
                )
            ),
            InlineQueryResultArticle(
                id="catalog-default",
                title="📂 Каталог",
                description="Специальные чаты",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "📂 Специальные чаты:\n\n"
                        "⭐ StarHub [Официальный чат]:\n"
                        "https://t.me/DeliciousStarHub\n\n"
                        "🍪 Пряники:\n"
                        "https://t.me/chatvaznihludey\n\n"
                        "🔪 Мафия:\n"
                        "https://t.me/DarkMafiaChat11"
                    )
                )
            ),
            InlineQueryResultArticle(
                id="specchat-default",
                title="✨ Сделать свой чат специальным",
                description="Сделать мой чат специальным",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "✨ Чтобы сделать свой чат специальным нужно:\n\n"
                        "1) Зайти в чат t.me/DeliciousStarHub.\n\n"
                        "2) Зайти в тему «Техническая поддержка» и написать сообщение с #спецчат.\n"
                        "В сообщение должна быть подробная информация о чате, о чем он, и тому подобная информация.\n\n"
                        "3) Ждать ответ админа/владельца, если чат по описанию подойдет вас попросят дать ссылку на чат в секретном сообщении @PPBBOT, чтобы убедиться, что вся информация правдива.\n"
                        "Если ваш чат подойдет, ваш чат попадет в каталог."
                    )
                )
            ),
            InlineQueryResultArticle(
                id="install_bots",
                title="Установка ботов",
                description="Установка ботов из звёздного семейства.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "🚀Установка:\n"
                        "1) Выберите бота:\n"
                        "@Star_def_bot.\n"
                        "@AIStar_ai_bot.\n"
                        "@Star_crypto_bot.\n"
                        "@DsStar_info_bot.\n\n"
                        "2) Зайдите в свой чат и выберите \"Добавить участников\".\n\n"
                        "3) Назначьте нужного бота администратором, выдавая все права.\n\n"
                        "4) Ознакомьтесь с командами."
                    )
                )
            ),
            InlineQueryResultArticle(
                id="star_commands",
                title="Команды звездного семейства",
                description="Все команды звёздного семейства.",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "📋 Список команд какого бота вас интересует?\n"
                        "Саппорта: https://telegra.ph/Komandy-StarSupportBot-07-15\n\n"
                        "Звездного семейства: https://telegra.ph/Komandy-zvezdnogo-semejstva-07-15"
                    )
                )
            )
        ]  

    await q.answer(results, cache_time=0, is_personal=True)


async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
