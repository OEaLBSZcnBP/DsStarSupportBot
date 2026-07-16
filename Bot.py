import os
import asyncio
import sqlite3
import math
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from aiogram.enums import ChatMemberStatus

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN not set")
    exit()

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = sqlite3.connect("moderation.db", check_same_thread=False)
db.execute("CREATE TABLE IF NOT EXISTS warns (user_id INTEGER, chat_id INTEGER, count INTEGER DEFAULT 0, last_warn DATETIME, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS mutes (user_id INTEGER, chat_id INTEGER, until DATETIME, PRIMARY KEY(user_id, chat_id))")
db.execute("CREATE TABLE IF NOT EXISTS bans (user_id INTEGER, chat_id INTEGER, until DATETIME, PRIMARY KEY(user_id, chat_id))")
db.commit()


def parse_time(time_str):
    match = re.match(r'^(\d+)([mhd])$', time_str)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    return None


def get_target_user(m: types.Message):
    if m.reply_to_message:
        return m.reply_to_message.from_user
    parts = m.text.split()
    for p in parts[1:]:
        if p.startswith("@"):
            try:
                chat = asyncio.run_coroutine_threadsafe(bot.get_chat(p), bot.loop).result()
                return chat
            except:
                pass
        elif p.lstrip("-").isdigit():
            try:
                chat = asyncio.run_coroutine_threadsafe(bot.get_chat(int(p)), bot.loop).result()
                return chat
            except:
                pass
    return None


def is_admin(user_id, chat_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = asyncio.run_coroutine_threadsafe(bot.get_chat_member(chat_id, user_id), bot.loop).result()
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except:
        return False


@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer(
        f"👋 Доброго времени суток, {m.from_user.first_name}!\n\n"
        f"🤖 Я бот-помощник для специальных чатов.\n\n"
        f"💡 У меня есть Inline mode — напишите в ЛС или в своем чате @DsStarSupportBot и тогда вы сможете его использовать."
    )


@dp.message(Command("commands", "команды"))
async def commands(m: types.Message):
    await m.answer(
        "📋 Команды:\n\n"
        "Модерация:\n"
        "/ban [время] @user\n"
        "/unban @user\n"
        "/mute [время] @user\n"
        "/unmute @user\n"
        "/warn @user\n"
        "/takewarn @user\n"
        "/wwarns @user\n"
        "/kick @user\n"
        "/report\n\n"
        "Прочее:\n"
        "/calculator 2+2*2\n"
        "/meta\n"
        "/offtop\n"
        "/search запрос\n"
        "/calc_pi"
    )


@dp.message(Command("ban", "бан"))
async def ban_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    args = m.text.split()
    if len(args) < 2:
        return await m.answer("❌ /ban 1h @user причина")
    duration = None
    if re.match(r'^\d+[mhd]$', args[1]):
        duration = parse_time(args[1])
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    until = None
    if duration:
        until = datetime.now().timestamp() + duration
        db.execute("INSERT OR REPLACE INTO bans VALUES (?, ?, ?)", (target.id, m.chat.id, until))
        db.commit()
    try:
        until_ts = int(until) if until else 0
        await bot.ban_chat_member(m.chat.id, target.id, until_date=until_ts)
        reason = " ".join(args[2:]) if len(args) > 2 else "Не указана"
        time_text = f"на {args[1]}" if duration else "навсегда"
        await m.answer(f"🔨 {target.first_name} забанен {time_text}\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("unban", "разбан"))
async def unban_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    try:
        await bot.unban_chat_member(m.chat.id, target.id)
        db.execute("DELETE FROM bans WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        await m.answer(f"✅ {target.first_name} разбанен")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("mute", "мут"))
async def mute_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    args = m.text.split()
    if len(args) < 2:
        return await m.answer("❌ /mute 1h @user причина")
    duration = parse_time(args[1]) if re.match(r'^\d+[mhd]$', args[1]) else 3600
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    until = datetime.now().timestamp() + duration
    db.execute("INSERT OR REPLACE INTO mutes VALUES (?, ?, ?)", (target.id, m.chat.id, until))
    db.commit()
    try:
        permissions = types.ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        await bot.restrict_chat_member(m.chat.id, target.id, permissions, until_date=int(until))
        reason = " ".join(args[2:]) if len(args) > 2 else "Не указана"
        await m.answer(f"🔇 {target.first_name} замучен на {args[1]}\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("unmute", "размут"))
async def unmute_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    try:
        permissions = types.ChatPermissions(
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
        )
        await bot.restrict_chat_member(m.chat.id, target.id, permissions)
        db.execute("DELETE FROM mutes WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
        db.commit()
        await m.answer(f"✅ {target.first_name} размучен")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("warn", "варн"))
async def warn_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    cur = db.execute("SELECT count FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    count = (row[0] if row else 0) + 1
    db.execute("INSERT OR REPLACE INTO warns (user_id, chat_id, count, last_warn) VALUES (?, ?, ?, ?)", (target.id, m.chat.id, count, datetime.now()))
    db.commit()
    if count >= 5:
        until = datetime.now().timestamp() + 30 * 86400
        db.execute("INSERT OR REPLACE INTO bans VALUES (?, ?, ?)", (target.id, m.chat.id, until))
        db.commit()
        try:
            await bot.ban_chat_member(m.chat.id, target.id, until_date=int(until))
            await m.answer(f"🔨 {target.first_name} получил 5/5 варнов и забанен на месяц")
        except:
            await m.answer(f"⚠️ 5/5 варнов у {target.first_name}")
    else:
        await m.answer(f"⚠️ {target.first_name}: {count}/5 варнов")


@dp.message(Command("takewarn", "снятьварн"))
async def take_warn(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    cur = db.execute("SELECT count FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    if not row or row[0] == 0:
        return await m.answer(f"❌ У {target.first_name} нет варнов")
    new_count = row[0] - 1
    db.execute("UPDATE warns SET count=? WHERE user_id=? AND chat_id=?", (new_count, target.id, m.chat.id))
    db.commit()
    await m.answer(f"✅ Снят варн у {target.first_name}. Теперь: {new_count}/5")


@dp.message(Command("wwarns", "варны"))
async def show_warns(m: types.Message):
    target = get_target_user(m)
    if not target:
        target = m.from_user
    cur = db.execute("SELECT count FROM warns WHERE user_id=? AND chat_id=?", (target.id, m.chat.id))
    row = cur.fetchone()
    count = row[0] if row else 0
    await m.answer(f"⚠️ {target.first_name}: {count}/5 варнов")


@dp.message(Command("kick", "кик"))
async def kick_user(m: types.Message):
    if not is_admin(m.from_user.id, m.chat.id):
        return await m.answer("❌ Только для админов")
    target = get_target_user(m)
    if not target:
        return await m.answer("❌ Юзер не найден")
    try:
        await bot.ban_chat_member(m.chat.id, target.id, until_date=int(datetime.now().timestamp()) + 30)
        await bot.unban_chat_member(m.chat.id, target.id)
        reason = " ".join(m.text.split()[1:]) if len(m.text.split()) > 1 else "Не указана"
        await m.answer(f"👢 {target.first_name} кикнут\n📝 Причина: {reason}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("report", "репорт"))
async def report(m: types.Message):
    if not m.reply_to_message:
        return await m.answer("❌ /report — реплай на сообщение нарушителя")
    target = m.reply_to_message.from_user
    reason = " ".join(m.text.split()[1:]) if len(m.text.split()) > 1 else "Не указана"
    try:
        admins = await bot.get_chat_administrators(m.chat.id)
        for admin in admins:
            if admin.user.id == bot.id:
                continue
            try:
                await bot.send_message(
                    admin.user.id,
                    f"🚨 Репорт!\n\n"
                    f"👤 От: {m.from_user.first_name} (@{m.from_user.username})\n"
                    f"👤 Нарушитель: {target.first_name} (@{target.username})\n"
                    f"💬 Чат: {m.chat.title}\n"
                    f"📝 Причина: {reason}\n\n"
                    f"💬 Сообщение: {m.reply_to_message.text or '[медиа]'}"
                )
            except:
                pass
        await m.answer("✅ Репорт отправлен админам")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("calculator", "калькулятор", "calc"))
async def calculator(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("❌ /calculator 2+2*2\nПоддержка: √, ^, π")
    expr = args[1]
    expr = expr.replace("√", "math.sqrt")
    expr = expr.replace("^", "**")
    expr = expr.replace("π", "math.pi")
    if any(c in expr for c in ["import", "os", "eval", "exec", "open", "__"]):
        return await m.answer("❌ Недопустимые символы")
    try:
        result = eval(expr, {"math": math, "__builtins__": {}})
        await m.answer(f"🧮 {args[1]} = {result}")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")


@dp.message(Command("calc_pi", "пи"))
async def calc_pi(m: types.Message):
    await m.answer(f"π = {math.pi}\n≈ 3.141592653589793")


@dp.message(Command("meta", "мета"))
async def meta(m: types.Message):
    await m.answer(
        "❓ Мета-вопросы:\n\n"
        "Это вопросы о самом боте, его работе, "
        "о Telegram или о том, как что-то устроено.\n\n"
        "Примеры:\n"
        "• Как ты работаешь?\n"
        "• Кто тебя создал?\n"
        "• Почему бот не отвечает?"
    )


@dp.message(Command("offtop", "оффтоп"))
async def offtop(m: types.Message):
    await m.answer(
        "🚫 Оффтоп:\n\n"
        "Сообщения не по теме чата.\n"
        "Флуд, спам, нецензурная брань — запрещены.\n"
        "За нарушение — мут/варн/бан."
    )


@dp.message(Command("search", "поиск"))
async def search(m: types.Message):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        return await m.answer("❌ /search запрос")
    query = args[1].replace(" ", "+")
    await m.answer(f"🔍 Яндекс:\nhttps://yandex.ru/search/?text={query}")


@dp.inline_query()
async def inline_handler(iq: types.InlineQuery):
    query = iq.query.lower().strip()
    results = []
    
    # 1) О ботах
    if not query or "о" in query or "бот" in query:
        results.append(types.InlineQueryResultArticle(
            id="1",
            title="О ботах",
            description="Краткое инфо о ботах: Python, Aiogram",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    "ℹ️ Краткое Инфо о ботах:\n\n"
                    "💬 Язык программирования: Python.\n"
                    "📖 Библиотека: Aiogram.\n"
                    "🤵‍♂️Кодер: @Luxscer"
                )
            )
        ))
    
    # 2) Каталог
    if not query or "каталог" in query or "чат" in query:
        results.append(types.InlineQueryResultArticle(
            id="2",
            title="Каталог",
            description="Специальные чаты: StarHub, Пряники, Мафия",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    "📂 Специальные чаты:\n\n"
                    "⭐ StarHub — https://t.me/StarHub\n"
                    "🍪 Пряники — https://t.me/StarHub_Pryaniki\n"
                    "🔪 Мафия — https://t.me/StarHub_Mafia"
                )
            )
        ))
    
    # 3) Спец чат
    if not query or "спец" in query or "свой" in query:
        results.append(types.InlineQueryResultArticle(
            id="3",
            title="Сделать свой чат специальным",
            description="Инструкция как сделать чат спец",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    "Чтобы сделать чат специальным:\n\n"
                    "1) Добавьте @DsStarSupportBot в чат\n"
                    "2) Назначьте бота администратором\n"
                    "3) Напишите в чат /special\n\n"
                    "Бот автоматически настроит чат."
                )
            )
        ))
    
    # 4) Установка ботов
    if not query or "установ" in query or "уст" in query:
        results.append(types.InlineQueryResultArticle(
            id="4",
            title="Установка ботов",
            description="Установка ботов из звёздного семейства",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    "Установка:\n"
                    "1) Выберите бота:\n"
                    "@Star_def_bot.\n"
                    "@AIStar_ai_bot.\n"
                    "@Star_crypto_bot.\n"
                    "@Starbots_payments_bot.\n\n"
                    "2) Зайдите в свой чат и выберите \"Добавить участников\".\n\n"
                    "3) Назначьте нужного бота администратором, выдая все права.\n\n"
                    "4) Ознакомьтесь с командами."
                )
            )
        ))
    
    # 5) Команды звездного семейства
    if not query or "команд" in query or "семейств" in query or "звездн" in query:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛡Саппорта", callback_data="cmd_support")],
            [InlineKeyboardButton(text="⭐ Звездного семейства", callback_data="cmd_star")]
        ])
        results.append(types.InlineQueryResultArticle(
            id="5",
            title="Команды звездного семейства",
            description="Все команды звёздного семейства",
            input_message_content=types.InputTextMessageContent(
                message_text="📋 Список команд какого бота вас интересует?",
                reply_markup=kb
            )
        ))
    
    if not results:
        results.append(types.InlineQueryResultArticle(
            id="0",
            title="DsStarSupportBot",
            description="Помощь по инлайн-режиму",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    "Инлайн-режим @DsStarSupportBot:\n\n"
                    "• О ботах\n"
                    "• Каталог\n"
                    "• Сделать свой чат специальным\n"
                    "• Установка ботов\n"
                    "• Команды звездного семейства"
                )
            )
        ))
    
    await iq.answer(results, cache_time=0)


@dp.callback_query(F.data.startswith("cmd_"))
async def cmd_callback(c: types.CallbackQuery):
    if c.data == "cmd_support":
        await c.message.edit_text(
            "📋 Команды @DsStarSupportBot:\n\n"
            "https://telegra.ph/Komandy-StarSupportBot-07-15"
        )
        await c.answer()
    elif c.data == "cmd_star":
        await c.message.edit_text(
            "📋 Команды звёздного семейства:\n\n"
            "https://telegra.ph/Komandy-zvezdnogo-semejstva-07-15"
        )
        await c.answer()


async def main():
    print("DsStarSupportBot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
