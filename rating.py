import os
import json
import asyncio
import time
from datetime import datetime, timedelta
# aiogram==2.25.1
from aiogram.utils import executor
from aiogram import Bot, Dispatcher, types
from aiogram.types import ChatAdministratorRights
from aiogram.contrib.middlewares.logging import LoggingMiddleware

def load_translations(file_path="translations.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

translations = load_translations()

TOKEN_FILE = "token.txt"
LANG_FILE = "lang.txt"
ADMIN_ID = 1808806022 # or your telegram-id
CREATOR_ID = 1808806022 # MIT License

# Слова для автоматического повышения баллов
THANK_WORDS = ["спасибо", "благодарю", "спс", "саул", "от души", "мерси", "спасибки",
               "thanks", "thank you", "thx", "благодарствуйте", "пасиб"]

# Время между благодарностями (5 минут в секундах)
THANK_COOLDOWN = 300  # 5 минут

# Время удаления командных сообщений (30 секунд)
COMMAND_DELETE_TIME = 30
# Время удаления уведомлений о повышении ранга (5 минут)
RANKUP_DELETE_TIME = 300

# to change the language, delete the contents of the file "lang.txt "and launch the bot.
LANG = ""

try:
    with open(LANG_FILE, 'r') as file:
        LANG = file.readline().strip()
        if LANG != "ru" and LANG != "eng":
            raise ValueError("Incorrect format.")
        elif LANG:
            print("INFO: The language is set.")
        else:
            raise ValueError("The file is empty.")
except (FileNotFoundError, ValueError):
    LANG = input("Enter the language('ru'/'eng'): ")

    while LANG != "ru" and LANG != "eng":
        LANG = input("Enter the language('ru'/'eng'): ")

    with open(LANG_FILE, 'w') as file:
        file.write(LANG)

    print("The language is saved.")

try:
    with open(TOKEN_FILE, 'r') as file:
        API_TOKEN = file.readline().strip()
        if API_TOKEN:
            print("INFO: The token was found.")
        else:
            raise ValueError("The file is empty.")
except (FileNotFoundError, ValueError):
    API_TOKEN = input("Enter your token: ")
    with open(TOKEN_FILE, 'w') as file:
        file.write(API_TOKEN)
    print("The token is saved.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Глобальные структуры данных
# user_points[chat_id][user_id] = {"username": "...", "points": X, "rank": "BASIC/PRO/ELITE"}
user_points = {}
# last_thank[chat_id][user_id] = timestamp последней благодарности
last_thank = {}
# Сохраняем последние ранги для определения повышения
last_ranks = {}

def get_points_file(chat_id):
    """Возвращает путь к файлу с баллами для конкретного чата"""
    # Преобразуем chat_id в строку и убираем знак минуса если есть
    chat_id_str = str(chat_id).replace('-', '')
    return f"points_{chat_id_str}.json"

def get_thank_file(chat_id):
    """Возвращает путь к файлу с временем последних благодарностей"""
    chat_id_str = str(chat_id).replace('-', '')
    return f"thank_{chat_id_str}.json"

def get_rank_file(chat_id):
    """Возвращает путь к файлу с последними рангами"""
    chat_id_str = str(chat_id).replace('-', '')
    return f"rank_{chat_id_str}.json"

def get_stars(points, is_owner=False):
    """Определяет количество звёзд в зависимости от баллов"""
    if points >= 30:
        return "★★★"
    elif points >= 15:
        return "★★☆"
    else:
        return "☆☆☆" if not is_owner else "★☆☆"

def get_level(points):
    """Определяет уровень (BASIC/PRO/ELITE)"""
    if points >= 30:
        return "ELITE"
    elif points >= 15:
        return "PRO"
    else:
        return "BASIC"

def get_rank_display(points, is_owner=False):
    """Возвращает статус для отображения: ★☆☆ BASIC [15] или ★☆☆ СМКЦ [15]"""
    stars = get_stars(points, is_owner=is_owner)

    if is_owner:
        level = "СМКЦ"
    else:
        level = get_level(points)

    return f"{stars} {level} [{points}]"

def get_rank_for_title(points, is_owner=False):
    """Возвращает статус для заголовка Telegram (укороченная версия)"""
    stars = get_stars(points, is_owner=is_owner)

    if is_owner:
        return f"{stars} СМКЦ [{points}]"
    else:
        level = get_level(points)
        return f"{stars} {level} [{points}]"

def load_chat_data(chat_id):
    """Загружает данные для конкретного чата"""
    points_file = get_points_file(chat_id)
    if os.path.exists(points_file):
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем строковые ключи в int
                return {int(k): v for k, v in data.items()}
        except json.JSONDecodeError:
            print(f"ERROR: Error reading points file for chat {chat_id}. Starting with empty data.")
        except Exception as e:
            print(f"ERROR loading chat data: {e}")
    return {}

def save_chat_data(chat_id, data):
    """Сохраняет данные для конкретного чата"""
    points_file = get_points_file(chat_id)

    try:
        with open(points_file, "w", encoding="utf-8") as f:
            data_to_save = {str(k): v for k, v in data.items()}
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"ERROR saving chat data: {e}")

def load_last_thanks(chat_id):
    """Загружает время последних благодарностей для чата"""
    thank_file = get_thank_file(chat_id)

    if os.path.exists(thank_file):
        try:
            with open(thank_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем ключи в int и значения в float (timestamp)
                return {int(k): float(v) for k, v in data.items()}
        except Exception as e:
            print(f"ERROR loading last thanks: {e}")
    return {}

def save_last_thanks(chat_id, data):
    """Сохраняет время последних благодарностей для чата"""
    thank_file = get_thank_file(chat_id)

    try:
        with open(thank_file, "w", encoding="utf-8") as f:
            data_to_save = {str(k): v for k, v in data.items()}
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"ERROR saving last thanks: {e}")

def load_last_ranks(chat_id):
    """Загружает последние ранги для чата"""
    rank_file = get_rank_file(chat_id)

    if os.path.exists(rank_file):
        try:
            with open(rank_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем строковые ключи в int
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            print(f"ERROR loading last ranks: {e}")
    return {}

def save_last_ranks(chat_id, data):
    """Сохраняет последние ранги для чата"""
    rank_file = get_rank_file(chat_id)

    try:
        with open(rank_file, "w", encoding="utf-8") as f:
            # Конвертируем int ключи в строки для сохранения
            data_to_save = {str(k): v for k, v in data.items()}
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"ERROR saving last ranks: {e}")

def get_translation(key, **kwargs):
    template = translations.get(LANG, {}).get(key, key)
    return template.format(**kwargs)

def contains_thank_word(text):
    """Проверяет, содержит ли текст слова благодарности (включая внутри других слов)"""
    if not text:
        return False

    text_lower = text.lower()
    for word in THANK_WORDS:
        if word in text_lower:
            return True
    return False

def can_thank_now(chat_id, user_id):
    """Проверяет, можно ли пользователю отправить благодарность"""
    # Загружаем данные для этого чата
    thanks_data = load_last_thanks(chat_id)

    if user_id in thanks_data:
        last_time = thanks_data[user_id]
        current_time = time.time()

        # Проверяем, прошло ли достаточно времени
        if current_time - last_time < THANK_COOLDOWN:
            return False, THANK_COOLDOWN - int(current_time - last_time)

    return True, 0

def update_last_thank(chat_id, user_id):
    """Обновляет время последней благодарности для пользователя"""
    thanks_data = load_last_thanks(chat_id)
    thanks_data[user_id] = time.time()
    save_last_thanks(chat_id, thanks_data)

print("\n" + "="*50)
print("🌟 СИСТЕМА СТАТУСОВ:")
print("☆☆☆ BASIC [0-14]")
print("★★☆ PRO [15-29]")
print("★★★ ELITE [30+]")
print("★☆☆ СМКЦ (для владельца)")
print("="*50 + "\n")

async def add_points_automatically(message, target_user_id, target_username):
    """Функция для автоматического добавления баллов"""
    chat_id = message.chat.id

    # Загружаем данные для этого чата
    chat_points = load_chat_data(chat_id)
    chat_last_ranks = load_last_ranks(chat_id)

    if target_user_id in chat_points:
        chat_points[target_user_id]["points"] += 1
        old_points = chat_points[target_user_id]["points"] - 1
        old_level = get_level(old_points)

        if chat_points[target_user_id]["username"] != target_username:
            chat_points[target_user_id]["username"] = target_username
    else:
        chat_points[target_user_id] = {"username": target_username, "points": 1}
        old_level = "BASIC"

    try:
        # Проверяем статус пользователя в чате
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']

        # Для НЕ-владельцев и НЕ-админов - повышаем до админа
        if not is_owner and member_status.status not in ['админ', 'administrator', 'bot-admin']:
            await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=target_user_id,
                can_manage_chat=False,
                can_post_messages=False,
                can_edit_messages=False,
                can_delete_messages=False,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
    except Exception as e:
        print(f"ERROR: {e}. Failed to issue a score.")
        await bot.send_message(chat_id=ADMIN_ID, text=f"Console by Kilobyte\nERROR: {e}. Failed to issue a score.")
        return False, old_level

    # Получаем новый статус с баллами
    new_points = chat_points[target_user_id]["points"]
    new_level = get_level(new_points)

    # Определяем, является ли пользователь владельцем
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        is_owner = False

    prefix = get_rank_for_title(new_points, is_owner=is_owner)

    try:
        # Устанавливаем префикс для всех пользователей (включая владельца)
        await bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=target_user_id,
            custom_title=prefix
        )
    except Exception as e:
        print(f"ERROR: {e}. Failed to set custom title.")
        # Для владельца может быть ошибка, но продолжаем
        if not is_owner:
            await bot.send_message(chat_id=ADMIN_ID, text=f"Console by Kilobyte\nERROR: {e}. Failed to set custom title.")
            return False, old_level

    # Сохраняем данные
    save_chat_data(chat_id, chat_points)

    # Проверяем повышение ранга
    rank_up = False
    if old_level != new_level and not is_owner:
        rank_up = True
        # Сохраняем новый ранг
        chat_last_ranks[target_user_id] = new_level
        save_last_ranks(chat_id, chat_last_ranks)

    # Выводим информацию в консоль о новом статусе
    user_type = "OWNER" if is_owner else "USER"
    print(f"STATUS UPDATE [{user_type}]: @{target_username} is now {prefix}")

    return True, old_level if not rank_up else new_level

async def send_rankup_notification(chat_id, username, old_rank, new_rank):
    """Отправляет уведомление о повышении ранга"""
    notification_text = f"""
🎉 УРА, У НАС ЗВЕЗДА! 🎉

@{username} поднял свой ранг и теперь он {new_rank}!

🌟 {old_rank} → {new_rank} 🌟

Поздравляем и гордимся твоим прогрессом!
Продолжай в том же духе! 💪✨
"""

    try:
        msg = await bot.send_message(chat_id=chat_id, text=notification_text)
        # Удаляем уведомление через 5 минут
        await asyncio.sleep(RANKUP_DELETE_TIME)
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception as e:
        print(f"ERROR sending rankup notification: {e}")

# ВАЖНО: Этот обработчик должен быть ПОСЛЕ обработчиков команд
@dp.message_handler(lambda message: message.text and not message.text.startswith('/') and message.reply_to_message)
async def check_thank_message(message: types.Message):
    """Проверяет только ответы (не команды) на наличие слов благодарности"""
    print(f"DEBUG: Проверяю сообщение от {message.from_user.id}: {message.text[:50]}...")

    # Проверяем кулдаун
    can_thank, wait_time = can_thank_now(message.chat.id, message.from_user.id)

    if not can_thank:
        # Молча игнорируем (как и просили)
        print(f"DEBUG: Кулдаун для {message.from_user.id}. Осталось ждать: {wait_time} сек")
        return

    # Проверяем, содержит ли сообщение слова благодарности
    if message.text and contains_thank_word(message.text):
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or f"user_{target_user_id}"

        print(f"DEBUG: Найдено слово благодарности, добавляем балл для {target_user_id}")

        # Обновляем время последней благодарности
        update_last_thank(message.chat.id, message.from_user.id)

        success, old_rank = await add_points_automatically(message, target_user_id, target_username)

        if success:
            # Отправляем уведомление и удаляем через 2 секунды
            thank_msg = "✅ +1 балл за благодарность!" if LANG == 'ru' else "✅ +1 point for thank you!"
            msg = await message.reply(thank_msg)
            await asyncio.sleep(2)
            try:
                await bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
            except:
                pass

            # Проверяем, было ли повышение ранга
            chat_points = load_chat_data(message.chat.id)
            if target_user_id in chat_points:
                new_points = chat_points[target_user_id]["points"]
                new_level = get_level(new_points)
                if old_rank in ["BASIC", "PRO"] and new_level != old_rank:
                    await send_rankup_notification(message.chat.id, target_username, old_rank, new_level)

async def delete_command_with_delay(message, response_msg, delay=COMMAND_DELETE_TIME):
    """Удаляет команду и ответ через указанное время"""
    await asyncio.sleep(delay)

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.delete_message(chat_id=response_msg.chat.id, message_id=response_msg.message_id)
    except Exception as e:
        print(f"ERROR deleting messages: {e}")

@dp.message_handler(commands=["help", "start"])
async def help_command(message: types.Message):
    """Команда помощи"""
    print(f"DEBUG: Обработчик /help вызван для {message.from_user.id}")

    help_text = """🎯 ДОСТУПНЫЕ КОМАНДЫ:

➕ Добавление баллов:
/add или /plus - добавить балл участнику (ответом на его сообщение)

📊 Информация:
/my - мой профиль (баллы и статус)
/top - ТОП-5 участников чата
/info - информация о системе репутации

⚙️ Админ-команды:
/update <ID> - обновить префикс пользователя

🤖 Автоматически:
Баллы добавляются при словах: спасибо, благодарю, спс, саул, от души, мерси, спасибки и др.
⚠️ Благодарить можно не чаще 1 раза в 5 минут"""

    msg = await message.reply(help_text)
    print(f"INFO: Отправлен ответ на /help пользователю {message.from_user.id}")

    # Запускаем удаление через 30 секунд
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["info"])
async def info(message: types.Message):
    """Информация о системе репутации"""
    print(f"DEBUG: Обработчик /info вызван для {message.from_user.id}")

    info_text = """🌟 СИСТЕМА РЕПУТАЦИИ

📊 Уровни статусов:
☆☆☆ BASIC [0-14] - Начинающий
★★☆ PRO [15-29] - Профессионал
★★★ ELITE [30+] - Элита
★☆☆ СМКЦ - Специальный статус владельца

🎯 Как получать баллы:
1. Ответьте /add на полезное сообщение
2. Поблагодарите участника словами: спасибо, благодарю, спс, саул, от души, мерси, спасибки
3. Получайте благодарности от других участников

⏰ Важные правила:
• Благодарить можно не чаще 1 раза в 5 минут
• При повышении ранга все участники увидят праздничное уведомление! 🎉

📈 Ваш статус отображается в префиксе над вашими сообщениями!"""

    msg = await message.reply(info_text)
    print(f"INFO: Отправлен ответ на /info пользователю {message.from_user.id}")

    # Запускаем удаление через 30 секунд
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["add", "plus", "pa", "добавить"])
async def add_points(message: types.Message):
    """Команда для ручного добавления балла"""
    print(f"DEBUG: Обработчик /add вызван для {message.from_user.id}")

    if not message.reply_to_message:
        msg = await message.reply("↩️ Ответьте этой командой на сообщение участника, чтобы добавить ему балл.")

        # Запускаем удаление через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or f"user_{target_user_id}"

    success, old_rank = await add_points_automatically(message, target_user_id, target_username)

    if success:
        # Показываем новый статус пользователя
        chat_points = load_chat_data(message.chat.id)
        if target_user_id in chat_points:
            new_points = chat_points[target_user_id]["points"]

            # Определяем, является ли пользователь владельцем
            try:
                member_status = await bot.get_chat_member(message.chat.id, target_user_id)
                is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
            except:
                is_owner = False

            new_rank_display = get_rank_display(new_points, is_owner=is_owner)

            status_msg = f"✅ {new_rank_display}\n└─ @{target_username}"
            msg = await message.reply(status_msg)

            # Запускаем удаление через 30 секунд
            asyncio.create_task(delete_command_with_delay(message, msg))

            # Проверяем, было ли повышение ранга
            if old_rank in ["BASIC", "PRO"] and get_level(new_points) != old_rank and not is_owner:
                new_rank = get_level(new_points)
                await send_rankup_notification(message.chat.id, target_username, old_rank, new_rank)

@dp.message_handler(commands=["my", "me", "profile"])
async def my_profile(message: types.Message):
    """Показать профиль текущего пользователя"""
    print(f"DEBUG: Обработчик /my вызван для {message.from_user.id}")

    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"

    # Загружаем данные для этого чата
    chat_points = load_chat_data(chat_id)

    if user_id in chat_points:
        user_balance = chat_points[user_id]['points']
    else:
        user_balance = 0

    # Определяем, является ли пользователь владельцем текущего чата
    try:
        member_status = await bot.get_chat_member(chat_id, user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except Exception as e:
        print(f"ERROR checking owner status: {e}")
        is_owner = False

    user_rank = get_rank_display(user_balance, is_owner=is_owner)

    # Определяем следующий уровень
    next_level = ""
    points_to_next = 0

    if is_owner:
        next_level = "▸ Максимальный статус достигнут"
    else:
        if user_balance < 15:
            next_level = "PRO"
            points_to_next = 15 - user_balance
        elif user_balance < 30:
            next_level = "ELITE"
            points_to_next = 30 - user_balance
        else:
            next_level = "▸ Максимальный уровень достигнут!"
            points_to_next = 0

    # Создаем красивый профиль
    profile_text = "👤 ПРОФИЛЬ УЧАСТНИКА\n\n"
    profile_text += f"🆔 ID: {user_id}\n"
    profile_text += f"📛 Имя: @{username}\n"
    profile_text += f"🏆 Баллы: {user_balance}\n\n"
    profile_text += f"⭐ Текущий статус:\n{user_rank}\n\n"

    if points_to_next > 0:
        profile_text += f"🎯 До {next_level}: {points_to_next} баллов\n"
        # Добавляем прогресс-бар
        if next_level == "PRO":
            progress = user_balance / 15 * 100
        else:  # ELITE
            progress = (user_balance - 15) / 15 * 100

        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        profile_text += f"📊 Прогресс: [{progress_bar}] {int(progress)}%\n"

    profile_text += "\n💡 Совет: Помогайте другим участникам\nи получайте благодарности для повышения репутации!"

    msg = await message.reply(profile_text)
    print(f"INFO: Отправлен ответ на /my пользователю {user_id}")

    # Запускаем удаление через 30 секунд
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["top", "рейтинг", "лидеры"])
async def top_players(message: types.Message):
    """Показать ТОП-5 участников"""
    print(f"DEBUG: Обработчик /top вызван для {message.from_user.id}")

    chat_id = message.chat.id
    chat_points = load_chat_data(chat_id)

    if not chat_points:
        msg = await message.reply("📭 Рейтинг пуст\nПока никто не получил баллов.")
        # Запускаем удаление через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, msg, 10))
        return

    # Сортируем пользователей по баллам
    sorted_users = sorted(
        chat_points.items(),
        key=lambda x: x[1]['points'],
        reverse=True
    )[:5]  # Берем топ-5

    # Создаем заголовок
    top_text = "🏆 ТОП-5 УЧАСТНИКОВ\n\n"

    for i, (user_id, user_data) in enumerate(sorted_users, 1):
        points = user_data['points']
        username = user_data.get('username', f"user_{user_id}")

        # Определяем, является ли пользователь владельцем
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
        except:
            is_owner = False

        rank_display = get_rank_display(points, is_owner=is_owner)

        # Вместо кликабельной ссылки - просто упоминание
        user_display = f"@{username}" if username else f"ID: {user_id}"

        # Добавляем медальку для первых мест
        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        top_text += f"{medal}{i}. {user_display}\n"
        top_text += f"   └─ {rank_display}\n\n"

    # Добавляем статистику
    total_players = len(chat_points)
    top_text += f"📊 Статистика: {total_players} участников в системе"

    msg = await message.reply(top_text)
    print(f"INFO: Отправлен ответ на /top пользователю {message.from_user.id}")

    # Запускаем удаление через 30 секунд
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["update", "u"])
async def update_prefix(message: types.Message):
    """Обновить префикс пользователя (админ)"""
    print(f"DEBUG: Обработчик /update вызван для {message.from_user.id}")

    command_args = message.get_args().strip()

    if not command_args:
        msg = await message.reply("ℹ️ Использование:\n/update <ID_пользователя>")
        # Запускаем удаление через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    try:
        target_user_id = int(command_args)
    except ValueError:
        msg = await message.reply("❌ Неверный ID пользователя")
        # Запускаем удаление через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    chat_id = message.chat.id
    chat_points = load_chat_data(chat_id)

    if target_user_id not in chat_points:
        msg = await message.reply("❌ Пользователь не найден в системе")
        # Запускаем удаление через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    user_data = chat_points[target_user_id]
    username = user_data.get('username', f"user_{target_user_id}")

    # Определяем, является ли пользователь владельцем
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        is_owner = False

    if not is_owner:
        try:
            if member_status.status not in ['админ', 'administrator', 'bot-admin']:
                await bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=target_user_id,
                    can_manage_chat=False,
                    can_post_messages=False,
                    can_edit_messages=False,
                    can_delete_messages=False,
                    can_manage_video_chats=False,
                    can_restrict_members=False,
                    can_promote_members=False,
                    can_change_info=False,
                    can_invite_users=True,
                    can_pin_messages=False
                )
        except Exception as e:
            print(f"ERROR: {e}. Failed to update prefix.")
            await bot.send_message(chat_id=ADMIN_ID, text=f"Console by Kilobyte\nERROR: {e}. Failed to update prefix.")
            return

    prefix = get_rank_for_title(user_data["points"], is_owner=is_owner)
    try:
        await bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=target_user_id,
            custom_title=prefix
        )
    except Exception as e:
        print(f"ERROR: {e}. Failed to update prefix.")
        if not is_owner:
            await bot.send_message(chat_id=ADMIN_ID, text=f"Console by Kilobyte\nERROR: {e}. Failed to update prefix.")
        return

    owner_text = " (владелец)" if is_owner else ""
    response = f"✅ Префикс обновлён\n\n"
    response += f"👤 Пользователь: @{username}{owner_text}\n"
    response += f"🆔 ID: {target_user_id}\n"
    response += f"⭐ Новый статус: {prefix}"

    msg = await message.reply(response)

    # Запускаем удаление через 30 секунд
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler()
async def catch_all_messages(message: types.Message):
    """Перехватывает все остальные сообщения для отладки"""
    print(f"DEBUG: Получено сообщение от {message.from_user.id}: {message.text}")

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН С ОБНОВЛЁННОЙ СИСТЕМОЙ РЕПУТАЦИИ!")
    print("=" * 60)
    print("\n🌟 СИСТЕМА СТАТУСОВ:")
    print("   ☆☆☆ BASIC [0-14]")
    print("   ★★☆ PRO [15-29]")
    print("   ★★★ ELITE [30+]")
    print("   ★☆☆ СМКЦ (только для владельца)")
    print("\n🎯 ДОСТУПНЫЕ КОМАНДЫ:")
    print("   /help - все команды")
    print("   /my - мой профиль")
    print("   /top - топ-5 участников")
    print("   /add - добавить балл (ответом)")
    print("   /info - о системе")
    print("   /update <ID> - обновить префикс")
    print("\n⏰ ОГРАНИЧЕНИЯ:")
    print("   • Благодарить можно 1 раз в 5 минут")
    print("   • Команды удаляются через 30 секунд")
    print("   • Каждая группа имеет отдельную базу данных")
    print("\n💬 Автоматическое повышение при словах:")
    print(f"   {', '.join(THANK_WORDS[:6])}...")
    print("=" * 60)
    executor.start_polling(dp, skip_updates=True)
# ────────────────────────────── ❑ ──────────────────────────────