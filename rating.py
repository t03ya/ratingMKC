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

def get_points_file(chat_id):
    """Возвращает путь к файлу с баллами для конкретного чата"""
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
        # ИСПРАВЛЕНИЕ: BASIC должен быть с одной звездочкой
        return "★☆☆" if not is_owner else "★☆☆"  # СМКЦ тоже с одной звездой

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
        # ИСПРАВЛЕНИЕ: Добавляем количество баллов в квадратных скобках
        return f"{stars} СМКЦ [{points}]"
    else:
        level = get_level(points)
        # ИСПРАВЛЕНИЕ: Добавляем количество баллов в квадратных скобках
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
            return {}
        except Exception as e:
            print(f"ERROR loading chat data: {e}")
            return {}
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
    thanks_data = load_last_thanks(chat_id)

    if user_id in thanks_data:
        last_time = thanks_data[user_id]
        current_time = time.time()

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
# ИСПРАВЛЕНИЕ: BASIC с одной звездой
print("★☆☆ BASIC [0-14]")
print("★★☆ PRO [15-29]")
print("★★★ ELITE [30+]")
print("★☆☆ СМКЦ (для владельца)")
print("="*50 + "\n")

async def make_user_admin_for_prefix(chat_id, user_id):
    """Делает пользователя администратором с минимальными правами для установки префикса"""
    try:
        print(f"DEBUG: Пытаюсь сделать пользователя {user_id} администратором в чате {chat_id}")
        
        # Сначала получаем текущий статус пользователя
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            current_status = member_status.status
            print(f"DEBUG: Текущий статус пользователя {user_id}: {current_status}")
            
            # Если уже админ или владелец, ничего не делаем
            if current_status in ['administrator', 'creator']:
                print(f"DEBUG: Пользователь {user_id} уже администратор")
                return True
        except Exception as e:
            print(f"DEBUG: Ошибка при получении статуса: {e}")
        
        # Делаем пользователя администратором с МИНИМАЛЬНЫМИ правами
        # Все права отключаем, чтобы у пользователя был только префикс
        success = await bot.promote_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_change_info=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_chat=False,
            can_manage_video_chats=False,
            can_manage_topics=False
        )
        
        if success:
            print(f"SUCCESS: Пользователь {user_id} успешно назначен администратором (с минимальными правами)")
            # Даем Telegram время обработать изменение прав
            await asyncio.sleep(1)
            return True
        else:
            print(f"ERROR: Не удалось назначить пользователя {user_id} администратором")
            return False
            
    except Exception as e:
        print(f"ERROR: Ошибка при назначении администратора: {e}")
        return False

async def set_user_prefix(chat_id, user_id, points, is_owner=False):
    """Устанавливает префикс пользователю"""
    try:
        # Формируем префикс с баллами
        prefix = get_rank_for_title(points, is_owner=is_owner)
        
        print(f"DEBUG: Устанавливаю префикс '{prefix}' для пользователя {user_id}")
        
        # Проверяем, является ли пользователь администратором
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            user_is_admin = member_status.status in ['administrator', 'creator']
            
            if not user_is_admin:
                print(f"DEBUG: Пользователь {user_id} не администратор, пытаюсь сделать админом...")
                # Пытаемся сделать пользователя администратором
                admin_success = await make_user_admin_for_prefix(chat_id, user_id)
                if not admin_success:
                    print(f"ERROR: Не удалось сделать пользователя {user_id} администратором для префикса")
                    return False
                # Даем время Telegram обработать
                await asyncio.sleep(1)
        except Exception as e:
            print(f"DEBUG: Ошибка при проверке статуса: {e}")
            return False
        
        # Устанавливаем кастомный заголовок (префикс)
        # Ограничение Telegram: максимум 16 символов
        prefix_to_set = prefix[:16]
        
        await bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=user_id,
            custom_title=prefix_to_set
        )
        
        print(f"SUCCESS: Префикс '{prefix_to_set}' установлен для пользователя {user_id}")
        return True
        
    except Exception as e:
        print(f"ERROR: Не удалось установить префикс: {e}")
        return False

async def add_points_automatically(message, target_user_id, target_username):
    """Функция для автоматического добавления баллов"""
    chat_id = message.chat.id

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

    # Определяем, является ли пользователь владельцем
    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
        print(f"DEBUG: Статус пользователя {target_user_id}: {member_status.status}, is_owner: {is_owner}")
    except Exception as e:
        print(f"WARNING: Could not get member status: {e}")

    new_points = chat_points[target_user_id]["points"]
    new_level = get_level(new_points)
    
    # ВАЖНО: Устанавливаем префикс КАЖДЫЙ РАЗ при начислении баллов
    # Это гарантирует, что префикс всегда актуальный
    prefix_success = await set_user_prefix(chat_id, target_user_id, new_points, is_owner)
    
    if prefix_success:
        print(f"SUCCESS: Префикс обновлен для {target_user_id} -> {get_rank_for_title(new_points, is_owner)}")
    else:
        print(f"WARNING: Не удалось обновить префикс для {target_user_id}")

    save_chat_data(chat_id, chat_points)

    rank_up = False
    if old_level != new_level and not is_owner:
        rank_up = True
        chat_last_ranks[target_user_id] = new_level
        save_last_ranks(chat_id, chat_last_ranks)

    user_type = "OWNER" if is_owner else "USER"
    print(f"STATUS UPDATE [{user_type}] in chat {chat_id}: @{target_username} is now {get_rank_for_title(new_points, is_owner)}")

    return True, old_level if not rank_up else new_level

async def send_rankup_notification(chat_id, username, old_rank, new_rank):
    """Отправляет уведомление о повышении ранга"""
    # ИСПРАВЛЕНИЕ: Исправляем отображение звезд
    old_stars = "★☆☆" if old_rank == "BASIC" else ("★★☆" if old_rank == "PRO" else "★★★")
    new_stars = "★☆☆" if new_rank == "BASIC" else ("★★☆" if new_rank == "PRO" else "★★★")
    
    notification_text = f"""
🎉 УРА, У НАС ЗВЕЗДА! 🎉

@{username} поднял свой ранг и теперь он {new_stars} {new_rank}!

🌟 {old_stars} {old_rank} → {new_stars} {new_rank} 🌟

Поздравляем и гордимся твоим прогрессом!
Продолжай в том же духе! 💪✨
"""

    try:
        msg = await bot.send_message(chat_id=chat_id, text=notification_text)
        await asyncio.sleep(RANKUP_DELETE_TIME)
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception as e:
        print(f"ERROR sending rankup notification: {e}")

# ИСПРАВЛЕНИЕ №3: Блокируем личные сообщения
@dp.message_handler(lambda message: message.chat.type == 'private')
async def block_private_messages(message: types.Message):
    """Блокирует любые сообщения в личных сообщениях"""
    print(f"BLOCKED: Private message from {message.from_user.id}: {message.text}")
    return  # Просто игнорируем

@dp.message_handler(lambda message: message.text and not message.text.startswith('/') and message.reply_to_message)
async def check_thank_message(message: types.Message):
    """Проверяет только ответы (не команды) на наличие слов благодарности"""
    # ИСПРАВЛЕНИЕ №3: Игнорируем личные сообщения
    if message.chat.type == 'private':
        return
        
    print(f"DEBUG: Проверяю сообщение в чате {message.chat.id} от {message.from_user.id}")

    can_thank, wait_time = can_thank_now(message.chat.id, message.from_user.id)

    if not can_thank:
        print(f"DEBUG: Кулдаун для {message.from_user.id}. Осталось ждать: {wait_time} сек")
        return

    if message.text and contains_thank_word(message.text):
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

        print(f"DEBUG: Найдено слово благодарности, добавляем балл для {target_user_id}")

        update_last_thank(message.chat.id, message.from_user.id)

        success, old_rank = await add_points_automatically(message, target_user_id, target_username)

        if success:
            thank_msg = "✅ +1 балл за благодарность!" if LANG == 'ru' else "✅ +1 point for thank you!"
            msg = await message.reply(thank_msg)
            await asyncio.sleep(2)
            try:
                await bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
            except:
                pass

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
    # ИСПРАВЛЕНИЕ №3: Блокируем команды в личных сообщениях
    if message.chat.type == 'private':
        return
        
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
⚠️ Благодарить можно не чаще 1 раза в 5 минут

⚠️ ВАЖНО О ПРЕФИКСАХ:
• Бот автоматически делает пользователей администраторами при первом начислении баллов
• Все административные права отключены (только префикс отображается)
• Префикс обновляется при каждом начислении баллов
• Формат префикса: ★☆☆ BASIC [8]"""

    msg = await message.reply(help_text)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["info"])
async def info(message: types.Message):
    """Информация о системе репутации"""
    if message.chat.type == 'private':
        return
        
    # ИСПРАВЛЕНИЕ: Исправляем отображение звезд
    info_text = """🌟 СИСТЕМА РЕПУТАЦИИ

📊 Уровни статусов:
★☆☆ BASIC [0-14] - Начинающий
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

📈 Автоматические действия:
• При первом начислении баллов бот сделает вас администратором (без прав)
• Ваш статус будет отображаться в префиксе над сообщениями: ★☆☆ BASIC [8]
• Префикс обновляется автоматически при каждом изменении баллов"""

    msg = await message.reply(info_text)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["add", "plus", "pa", "добавить"])
async def add_points(message: types.Message):
    """Команда для ручного добавления балла"""
    if message.chat.type == 'private':
        return
        
    if not message.reply_to_message:
        msg = await message.reply("↩️ Ответьте этой командой на сообщение участника, чтобы добавить ему балл.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

    success, old_rank = await add_points_automatically(message, target_user_id, target_username)

    if success:
        chat_points = load_chat_data(message.chat.id)
        if target_user_id in chat_points:
            new_points = chat_points[target_user_id]["points"]

            is_owner = False
            try:
                member_status = await bot.get_chat_member(message.chat.id, target_user_id)
                is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
            except:
                pass

            new_rank_display = get_rank_display(new_points, is_owner=is_owner)

            status_msg = f"✅ {new_rank_display}\n└─ @{target_username if target_username.startswith('@') else f'@{target_username}' if '@' not in target_username else target_username}"
            msg = await message.reply(status_msg)
            asyncio.create_task(delete_command_with_delay(message, msg))

            if old_rank in ["BASIC", "PRO"] and get_level(new_points) != old_rank and not is_owner:
                new_rank = get_level(new_points)
                await send_rankup_notification(message.chat.id, target_username, old_rank, new_rank)

@dp.message_handler(commands=["my", "me", "profile"])
async def my_profile(message: types.Message):
    """Показать профиль текущего пользователя"""
    if message.chat.type == 'private':
        return
        
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or f"user_{user_id}"

    chat_points = load_chat_data(chat_id)

    if user_id in chat_points:
        user_balance = chat_points[user_id]['points']
    else:
        user_balance = 0

    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except Exception as e:
        print(f"ERROR checking owner status: {e}")

    user_rank = get_rank_display(user_balance, is_owner=is_owner)

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

    profile_text = "👤 ПРОФИЛЬ УЧАСТНИКА\n\n"
    profile_text += f"🆔 ID: {user_id}\n"
    profile_text += f"📛 Имя: @{username}\n"
    profile_text += f"🏆 Баллы: {user_balance}\n\n"
    profile_text += f"⭐ Текущий статус:\n{user_rank}\n\n"

    if points_to_next > 0:
        profile_text += f"🎯 До {next_level}: {points_to_next} баллов\n"
        if next_level == "PRO":
            progress = user_balance / 15 * 100
        else:  # ELITE
            progress = (user_balance - 15) / 15 * 100

        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        profile_text += f"📊 Прогресс: [{progress_bar}] {int(progress)}%\n"

    profile_text += "\n💡 Совет: Помогайте другим участникам\nи получайте благодарности для повышения репутации!"

    msg = await message.reply(profile_text)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["top", "рейтинг", "лидеры"])
async def top_players(message: types.Message):
    """Показать ТОП-5 участников"""
    if message.chat.type == 'private':
        return
        
    chat_id = message.chat.id
    chat_points = load_chat_data(chat_id)

    if not chat_points:
        msg = await message.reply("📭 Рейтинг пуст\nПока никто не получил баллов.")
        asyncio.create_task(delete_command_with_delay(message, msg, 10))
        return

    sorted_users = sorted(
        chat_points.items(),
        key=lambda x: x[1]['points'],
        reverse=True
    )[:5]

    top_text = "🏆 ТОП-5 УЧАСТНИКОВ\n\n"

    for i, (user_id, user_data) in enumerate(sorted_users, 1):
        points = user_data['points']
        username = user_data.get('username', f"user_{user_id}")

        is_owner = False
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
        except:
            pass

        rank_display = get_rank_display(points, is_owner=is_owner)

        # ИСПРАВЛЕНИЕ: Создаем ссылку на профиль через user_id вместо юзернейма
        user_display = f"<a href='tg://user?id={user_id}'>{username}</a>"

        medal = ""
        if i == 1:
            medal = "🥇 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "

        top_text += f"{medal}{i}. {user_display}\n"
        top_text += f"   └─ {rank_display}\n\n"

    total_players = len(chat_points)
    top_text += f"📊 Статистика: {total_players} участников в системе"

    # ИСПРАВЛЕНИЕ: Отправляем как HTML для поддержки ссылок
    msg = await message.reply(top_text, parse_mode="HTML")
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["update", "u"])
async def update_prefix(message: types.Message):
    """Обновить префикс пользователя (админ)"""
    if message.chat.type == 'private':
        return
        
    command_args = message.get_args().strip()

    if not command_args:
        msg = await message.reply("ℹ️ Использование:\n/update <ID_пользователя>\n\nПример: /update 123456789")
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    try:
        target_user_id = int(command_args)
    except ValueError:
        msg = await message.reply("❌ Неверный ID пользователя")
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    chat_id = message.chat.id
    chat_points = load_chat_data(chat_id)

    if target_user_id not in chat_points:
        msg = await message.reply("❌ Пользователь не найден в системе")
        asyncio.create_task(delete_command_with_delay(message, msg))
        return

    user_data = chat_points[target_user_id]
    username = user_data.get('username', f"user_{target_user_id}")

    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        pass

    # ВАЖНОЕ ИСПРАВЛЕНИЕ: Формат префикса с баллами
    prefix = get_rank_for_title(user_data["points"], is_owner=is_owner)
    
    print(f"DEBUG: Обновляю префикс пользователя {target_user_id} на '{prefix}'")
    
    # Используем ту же функцию, что и для автоматического обновления
    prefix_success = await set_user_prefix(chat_id, target_user_id, user_data["points"], is_owner)
    
    if prefix_success:
        success_msg = f"✅ Префикс '{prefix}' успешно установлен!"
    else:
        success_msg = f"❌ Не удалось установить префикс. Убедитесь, что бот администратор и имеет права на назначение администраторов."

    owner_text = " (владелец)" if is_owner else ""
    response = f"{success_msg}\n\n"
    # ИСПРАВЛЕНИЕ: Используем ссылку на профиль
    response += f"👤 Пользователь: <a href='tg://user?id={target_user_id}'>{username}</a>{owner_text}\n"
    response += f"🆔 ID: {target_user_id}\n"
    response += f"⭐ Текущий статус: {prefix}"

    msg = await message.reply(response, parse_mode="HTML")
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler()
async def catch_all_messages(message: types.Message):
    """Перехватывает все остальные сообщения"""
    # ИСПРАВЛЕНИЕ: Игнорируем личные сообщения
    if message.chat.type == 'private':
        print(f"BLOCKED: Private message from {message.from_user.id}")
        return
    print(f"DEBUG: Message in chat {message.chat.id} from {message.from_user.id}: {message.text}")

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН С ОБНОВЛЁННОЙ СИСТЕМОЙ РЕПУТАЦИИ!")
    print("=" * 60)
    print("\n🌟 СИСТЕМА СТАТУСОВ:")
    print("   ★☆☆ BASIC [0-14]")
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
    print("\n⚠️ АВТОМАТИЧЕСКИЕ ДЕЙСТВИЯ:")
    print("   1. Бот автоматически делает пользователей администраторами")
    print("   2. Все административные права отключены")
    print("   3. Префикс отображается в виде: ★☆☆ BASIC [8]")
    print("   4. Префикс обновляется при КАЖДОМ начислении баллов")
    print("\n⏰ ОГРАНИЧЕНИЯ:")
    print("   • Благодарить можно 1 раз в 5 минут")
    print("   • Команды удаляются через 30 секунд")
    print("   • Каждая группа имеет отдельную базу данных")
    print("   • Бот игнорирует личные сообщения")
    print("\n💬 Автоматическое повышение при словах:")
    print(f"   {', '.join(THANK_WORDS[:6])}...")
    print("=" * 60)
    executor.start_polling(dp, skip_updates=True)
