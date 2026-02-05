import os
import json
import asyncio
import time
import re
import glob
import threading
import queue
from datetime import datetime, timedelta
from collections import defaultdict
# aiogram==2.25.1
from aiogram.utils import executor
from aiogram import Bot, Dispatcher, types
from aiogram.types import ChatAdministratorRights, MessageReactionUpdated
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# Глобальные очереди для обработки благодарностей
thank_queue = asyncio.Queue()
processing_tasks = {}
processing_lock = asyncio.Lock()

# ДОБАВЛЕНО: Словарь для блокировок файлов (упрощенный)
file_locks = {}

def load_translations(file_path="translations.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

translations = load_translations()

TOKEN_FILE = "token.txt"
LANG_FILE = "lang.txt"
ADMIN_ID = 1808806022 # or your telegram-id
CREATOR_ID = 8331388910 # ID создателя (ваш ID) - ЗАЩИЩЕННЫЕ КОМАНДЫ

# Слова для автоматического повышения баллов
THANK_WORDS = ["спасибо", "благодарю", "спс", "саул", "от души", "мерси", "спасибки",
               "thanks", "thank you", "thx", "благодарствуйте", "пасиб"]

# ДОБАВЛЕНО: Эмодзи для реакции рукопожатия
HANDSHAKE_EMOJI = "🤝"

# ИЗМЕНЕНО: Удалено время между благодарностями
# Теперь можно благодарить без ограничений

# Время удаления командных сообщений (30 секунд) - по умолчанию
COMMAND_DELETE_TIME = 30
# Время удаления уведомлений о повышении ранга (5 минут)
RANKUP_DELETE_TIME = 300

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

def get_stars(points):
    """Определяет количество звёзд в зависимости от баллов"""
    if points >= 30:
        return "★★★"
    elif points >= 15:
        return "★★☆"
    else:
        return "★☆☆"

def get_level(points):
    """Определяет уровень (для внутреннего использования)"""
    if points >= 30:
        return "ELITE"
    elif points >= 15:
        return "PRO"
    else:
        return "BASIC"

def get_rank_display(points, is_owner=False):
    """Возвращает статус для отображения: ★☆☆ [15]"""
    stars = get_stars(points)
    return f"{stars} [{points}]"

def get_rank_for_title(points, is_owner=False):
    """Возвращает статус для заголовка Telegram (укороченная версия)"""
    stars = get_stars(points)
    return f"{stars} [{points}]"

# УПРОЩЕННЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ
def load_chat_data(chat_id):
    """Загружает данные для конкретного чата"""
    points_file = get_points_file(chat_id)

    if os.path.exists(points_file):
        try:
            with open(points_file, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        if word.lower() in text_lower:  # Сравниваем в нижнем регистре
            return True
    return False

# ИЗМЕНЕНО: Упрощенная функция - всегда возвращает True (нет ограничений)
async def can_thank_now(chat_id, user_id):
    """Проверяет, можно ли пользователю отправить благодарность"""
    # Теперь всегда возвращаем True - ограничений нет
    return True, 0

def extract_points_from_command(text):
    """Извлекает количество баллов и причину из команды /plus или /minus"""
    # Убираем команду и оставляем только аргументы
    if text.startswith('/plus '):
        text = text[6:]
    elif text.startswith('/minus '):
        text = text[7:]

    # Ищем число в начале текста
    match = re.match(r'^(\d+)\s*(.*)', text.strip())
    if match:
        points = int(match.group(1))
        reason = match.group(2).strip()
        return points, reason if reason else "без указания причины"

    # Ищем число в конце текста
    match = re.search(r'(\d+)$', text.strip())
    if match:
        points = int(match.group(1))
        reason = text.replace(match.group(1), '').strip()
        return points, reason if reason else "без указания причины"

    return 0, ""

async def get_user_id_from_mention(chat_id, username_input):
    """Получает ID пользователя по username - исправленная версия"""
    try:
        username = username_input.lstrip('@')

        chat_points = load_chat_data(chat_id)

        for user_id, user_data in chat_points.items():
            user_username = user_data.get('username', '').lstrip('@')
            if user_username and user_username.lower() == username.lower():
                return user_id

        return None

    except Exception as e:
        print(f"ERROR: Не удалось найти пользователя @{username_input}: {e}")
        return None

async def make_user_admin_for_prefix(chat_id, user_id):
    """Делает пользователя администратором с минимальными правами для установки префикса"""
    try:
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            if member_status.status in ['administrator', 'creator']:
                return True
        except Exception as e:
            print(f"DEBUG: Ошибка при получении статуса: {e}")

        # Делаем пользователя администратором с МИНИМАЛЬНЫМИ правами
        try:
            success = await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=False,
                can_post_messages=False,
                can_edit_messages=False,
                can_delete_messages=False,
                can_invite_users=True,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False,
                can_manage_chat=False,
                can_manage_video_chats=False,
                can_manage_topics=False
            )

            if success:
                await asyncio.sleep(2)
                return True
            else:
                return False

        except Exception as e:
            print(f"ERROR: Исключение при назначении администратора: {e}")
            return False

    except Exception as e:
        print(f"ERROR: Общая ошибка при назначении администратора: {e}")
        return False

async def set_user_prefix(chat_id, user_id, points, is_owner=False):
    """Устанавливает префикс пользователю - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    try:
        # Формируем префикс с баллами (только звезды и баллы)
        prefix = get_rank_for_title(points, is_owner=is_owner)

        # Проверяем статус пользователя
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            user_is_admin = member_status.status in ['administrator', 'creator']

            if not user_is_admin:
                admin_success = await make_user_admin_for_prefix(chat_id, user_id)
                if not admin_success:
                    return False
                await asyncio.sleep(2)

            # Теперь пробуем установить префикс
            # Ограничение Telegram: максимум 16 символов для префикса
            prefix_to_set = prefix[:16]

            # Попробуем установить префикс несколько раз
            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    await bot.set_chat_administrator_custom_title(
                        chat_id=chat_id,
                        user_id=user_id,
                        custom_title=prefix_to_set
                    )
                    return True

                except Exception as e:
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2)
                    else:
                        return False

        except Exception as e:
            return False

    except Exception as e:
        return False

async def register_user_if_not_exists(chat_id, user_id, username):
    """Регистрирует пользователя в базе данных, если его там еще нет"""
    try:
        chat_points = load_chat_data(chat_id)

        if user_id not in chat_points:
            chat_points[user_id] = {"username": username, "points": 0}
            save_chat_data(chat_id, chat_points)
            print(f"✅ Зарегистрирован новый пользователь: @{username} (ID: {user_id})")
            return True
        return False
    except Exception as e:
        print(f"❌ Ошибка при регистрации пользователя {user_id}: {e}")
        return False

async def change_user_points_by_reply(message, points_change, is_addition=True, reason=""):
    """Изменяет баллы пользователя в ответ на сообщение и обновляет префикс"""
    chat_id = message.chat.id

    if not message.reply_to_message:
        return False, "❌ Эта команда должна быть отправлена в ответ на сообщение пользователя!"

    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

    # АВТОМАТИЧЕСКАЯ РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ, ЕСЛИ ЕГО НЕТ В БАЗЕ
    await register_user_if_not_exists(chat_id, target_user_id, target_username)

    try:
        # Загружаем данные
        chat_points = load_chat_data(chat_id)
        chat_last_ranks = load_last_ranks(chat_id)

        # Теперь пользователь точно есть в базе (мы его зарегистрировали)
        old_points = chat_points[target_user_id]["points"]
        old_level = get_level(old_points)

        if is_addition:
            new_points = old_points + points_change
            action_word = "добавлено"
        else:
            new_points = max(0, old_points - points_change)
            action_word = "вычтено"

        chat_points[target_user_id]["points"] = new_points

        is_owner = False
        try:
            member_status = await bot.get_chat_member(chat_id, target_user_id)
            is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
        except:
            pass

        new_level = get_level(new_points)

        # Сохраняем данные
        save_chat_data(chat_id, chat_points)

        rank_change = ""
        if old_level != new_level and not is_owner:
            rank_change = f"\n🎉 Изменение ранга: {old_level} → {new_level}"
            chat_last_ranks[target_user_id] = new_level
            save_last_ranks(chat_id, chat_last_ranks)

        # Устанавливаем префикс
        prefix_success = await set_user_prefix(chat_id, target_user_id, new_points, is_owner)

        if prefix_success:
            prefix_msg = "✅ Префикс обновлен"
        else:
            prefix_msg = "⚠️ Не удалось установить префикс (проверьте права бота)"

        # Формируем сообщение с причиной
        reason_text = f"\n📝 Причина: {reason}" if reason else ""

        result_msg = f"""✅ Успешно! {action_word} {points_change} баллов.

👤 Пользователь: @{target_username}
📊 Было: {old_points} | Стало: {new_points}
⭐ Новый статус: {get_rank_display(new_points, is_owner)}
{prefix_msg}{rank_change}{reason_text}"""

        return True, result_msg

    except Exception as e:
        print(f"❌ Ошибка в change_user_points_by_reply: {e}")
        return False, f"❌ Ошибка при изменении баллов: {str(e)}"

print("\n" + "="*50)
print("🌟 СИСТЕМА СТАТУСОВ:")
print("★☆☆ [0-14]")
print("★★☆ [15-29]")
print("★★★ [30+]")
print("="*50 + "\n")

# НОВАЯ: Улучшенная функция для обработки благодарностей
async def process_thank_task(chat_id, sender_id, target_user_id, target_username, message_id, reaction=False):
    """Обрабатывает одну благодарность или реакцию"""
    print(f"🔄 Обработка {'реакции' if reaction else 'благодарности'}: от {sender_id} для {target_user_id} в чате {chat_id}")

    try:
        # Регистрируем пользователя если нужно
        await register_user_if_not_exists(chat_id, target_user_id, target_username)

        # Загружаем данные
        chat_points = load_chat_data(chat_id)
        chat_last_ranks = load_last_ranks(chat_id)

        # Получаем текущие баллы
        if target_user_id not in chat_points:
            chat_points[target_user_id] = {"username": target_username, "points": 0}

        old_points = chat_points[target_user_id]["points"]
        old_level = get_level(old_points)

        # Добавляем балл
        chat_points[target_user_id]["points"] = old_points + 1
        new_points = chat_points[target_user_id]["points"]
        new_level = get_level(new_points)

        print(f"📊 Начислен балл: {target_user_id} ({old_points} → {new_points})")

        # Сохраняем данные
        save_chat_data(chat_id, chat_points)

        # Проверяем повышение ранга
        if old_level != new_level:
            chat_last_ranks[target_user_id] = new_level
            save_last_ranks(chat_id, chat_last_ranks)
            print(f"🎉 Повышение ранга: {old_level} → {new_level}")

        # Устанавливаем префикс
        try:
            member_status = await bot.get_chat_member(chat_id, target_user_id)
            is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
        except:
            is_owner = False

        if not is_owner:
            await set_user_prefix(chat_id, target_user_id, new_points, is_owner)

        # Отправляем уведомление (только для реакций или если не reaction)
        if reaction:
            try:
                thank_msg = f"✅ +1 балл за реакцию {HANDSHAKE_EMOJI}!"
                msg = await bot.send_message(chat_id=chat_id, text=thank_msg, reply_to_message_id=message_id)

                # Удаляем через 10 секунд
                await asyncio.sleep(10)
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                except:
                    pass
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление: {e}")
        else:
            # Для обычных благодарностей отправляем уведомление
            try:
                thank_msg = "✅ +1 балл за благодарность!"
                msg = await bot.send_message(chat_id=chat_id, text=thank_msg, reply_to_message_id=message_id)

                # Удаляем через 10 секунд
                await asyncio.sleep(10)
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                except:
                    pass
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление: {e}")

        # Если было повышение ранга, отправляем уведомление
        if old_level != new_level and not is_owner:
            await send_rankup_notification(chat_id, target_username, old_level, new_level)

        print(f"✅ {'Реакция' if reaction else 'Благодарность'} успешно обработана")
        return True

    except Exception as e:
        print(f"❌ Ошибка при обработке {'реакции' if reaction else 'благодарности'}: {e}")
        import traceback
        traceback.print_exc()
        return False

# НОВАЯ: Функция для добавления задачи в очередь
async def add_thank_to_queue(chat_id, sender_id, target_user_id, target_username, message_id, reaction=False):
    """Добавляет благодарность или реакцию в очередь на обработку"""
    try:
        # Создаем уникальный ключ для этой операции
        operation_key = f"{chat_id}_{sender_id}_{target_user_id}_{time.time()}"

        # Создаем задачу обработки
        task = asyncio.create_task(
            process_thank_task(chat_id, sender_id, target_user_id, target_username, message_id, reaction)
        )

        # Сохраняем задачу
        async with processing_lock:
            processing_tasks[operation_key] = task

        # Ждем завершения задачи
        result = await task

        # Удаляем задачу из списка
        async with processing_lock:
            if operation_key in processing_tasks:
                del processing_tasks[operation_key]

        return result

    except Exception as e:
        print(f"❌ Ошибка при добавлении в очередь: {e}")
        return False

# ДОБАВЛЕНО: Функция для проверки наличия реакции рукопожатия
def has_handshake_reaction(reactions):
    """Проверяет, есть ли среди реакций рукопожатие 🤝"""
    if not reactions:
        return False

    for reaction in reactions:
        # Проверяем разные типы реакции
        if hasattr(reaction, 'emoji'):
            if hasattr(reaction.emoji, 'emoji'):
                # Это обычный эмодзи (ReactionTypeEmoji)
                if reaction.emoji.emoji == HANDSHAKE_EMOJI:
                    return True
            elif isinstance(reaction.emoji, str):
                # Это строковый эмодзи
                if reaction.emoji == HANDSHAKE_EMOJI:
                    return True
    return False

async def send_rankup_notification(chat_id, username, old_rank, new_rank):
    old_stars = "★☆☆" if old_rank == "BASIC" else ("★★☆" if old_rank == "PRO" else "★★★")
    new_stars = "★☆☆" if new_rank == "BASIC" else ("★★☆" if new_rank == "PRO" else "★★★")

    notification_text = f"""
🎉 УРА, У НАС ЗВЕЗДА! 🎉

@{username} поднял свой ранг и теперь он {new_stars} {new_rank}!

🌟 {old_stars} {old_rank} → {new_stars} {new_rank} 🌟

Продолжай в том же духе! 💪✨
"""

    try:
        msg = await bot.send_message(chat_id=chat_id, text=notification_text)
        await asyncio.sleep(RANKUP_DELETE_TIME)
        await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception as e:
        print(f"ERROR sending rankup notification: {e}")

async def delete_command_with_delay(message, response_msg, delay=COMMAND_DELETE_TIME):
    """Удаляет сообщения с задержкой"""
    await asyncio.sleep(delay)

    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.delete_message(chat_id=response_msg.chat.id, message_id=response_msg.message_id)
    except Exception as e:
        print(f"ERROR deleting messages: {e}")

async def register_all_chat_members(chat_id):
    """Регистрирует всех участников чата в базе данных с рейтингом 0"""
    try:
        print(f"🔄 Регистрирую всех участников чата {chat_id}")

        # Получаем список участников чата
        members_count = 0
        registered_count = 0

        try:
            # Пробуем получить участников (может не работать в больших группах)
            async for member in bot.get_chat_members(chat_id, limit=200):
                members_count += 1
                user_id = member.user.id
                username = member.user.username or member.user.first_name or f"user_{user_id}"

                # Загружаем текущие данные
                chat_points = load_chat_data(chat_id)

                # Если пользователя еще нет в базе, добавляем его
                if user_id not in chat_points:
                    chat_points[user_id] = {"username": username, "points": 0}
                    registered_count += 1

                # Сохраняем обновленные данные
                save_chat_data(chat_id, chat_points)

                # Небольшая задержка чтобы не спамить API
                await asyncio.sleep(0.05)

        except Exception as e:
            print(f"⚠️ Не удалось получить всех участников чата {chat_id}: {e}")

        print(f"✅ В чате {chat_id}: {members_count} участников, зарегистрировано новых: {registered_count}")
        return registered_count

    except Exception as e:
        print(f"❌ Ошибка при регистрации участников чата {chat_id}: {e}")
        return 0

async def update_all_prefixes_on_start():
    """Обновляет все префиксы при запуске бота"""
    print("🔄 Начинаю обновление префиксов при запуске бота...")

    # Ищем все файлы с данными чатов
    points_files = glob.glob("points_*.json")

    for points_file in points_files:
        try:
            # Извлекаем chat_id из имени файла
            chat_id_str = points_file.replace("points_", "").replace(".json", "")
            chat_id = int(chat_id_str)

            # Загружаем данные чата
            chat_points = load_chat_data(chat_id)

            if not chat_points:
                continue

            print(f"🔄 Обновляю префиксы для чата {chat_id} ({len(chat_points)} пользователей)")

            # Обновляем префиксы для каждого пользователя
            for user_id, user_data in chat_points.items():
                try:
                    points = user_data["points"]

                    # Проверяем, является ли пользователь владельцем
                    is_owner = False
                    try:
                        member_status = await bot.get_chat_member(chat_id, user_id)
                        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
                    except Exception as e:
                        print(f"DEBUG: Не удалось получить статус пользователя {user_id}: {e}")

                    # Обновляем префикс
                    prefix_success = await set_user_prefix(chat_id, user_id, points, is_owner)
                    if prefix_success:
                        print(f"✅ Префикс обновлен для пользователя {user_id}")
                    else:
                        print(f"⚠️ Не удалось обновить префикс для пользователя {user_id}")

                    await asyncio.sleep(0.5)  # Небольшая задержка чтобы не спамить API

                except Exception as e:
                    print(f"❌ Ошибка при обновлении префикса для пользователя {user_id}: {e}")

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {points_file}: {e}")

    print("✅ Обновление префиксов завершено!")

async def send_restart_notification():
    """Отправляет уведомление о перезапуске во все чаты"""
    print("📢 Отправляю уведомления о перезапуске...")

    points_files = glob.glob("points_*.json")
    successful_sends = 0
    failed_sends = 0

    for points_file in points_files:
        try:
            chat_id_str = points_file.replace("points_", "").replace(".json", "")
            chat_id = int(chat_id_str)

            try:
                # Пытаемся отправить сообщение - если чат не найден, будет исключение
                restart_msg = "🤖 Бот был перезапущен. Все префиксы обновлены!"
                msg = await bot.send_message(chat_id=chat_id, text=restart_msg)
                successful_sends += 1
                print(f"✅ Уведомление отправлено в чат {chat_id}")

                # Удаляем через 10 секунд
                await asyncio.sleep(10)
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
                    print(f"✅ Уведомление удалено из чата {chat_id}")
                except Exception as delete_e:
                    print(f"⚠️ Не удалось удалить уведомление из чата {chat_id}: {delete_e}")

                await asyncio.sleep(1)  # Задержка между чатами

            except Exception as e:
                failed_sends += 1
                # Проверяем, что это именно ошибка "Chat not found", а не другие ошибки
                if "Chat not found" in str(e) or "чат не найден" in str(e).lower():
                    print(f"⚠️ Чат {chat_id} не найден (бот был удален из чата)")
                elif "bot was blocked" in str(e).lower() or "бот заблокирован" in str(e).lower():
                    print(f"⚠️ Бот заблокирован в чате {chat_id}")
                elif "chat not found" in str(e).lower():
                    print(f"⚠️ Чат {chat_id} не найден")
                else:
                    print(f"❌ Не удалось отправить уведомление в чат {chat_id}: {e}")

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {points_file}: {e}")

    print(f"✅ Уведомления о перезапуске отправлены! Успешно: {successful_sends}, Неудачно: {failed_sends}")

# ДОБАВЛЕНО: Обработчик для новых участников чата
@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def on_new_chat_members(message: types.Message):
    """Обработчик для новых участников чата (включая бота)"""
    chat_id = message.chat.id

    print(f"🆕 Новые участники в чате {chat_id}")

    # Обрабатываем всех новых участников
    for new_member in message.new_chat_members:
        user_id = new_member.id
        username = new_member.username or new_member.first_name or f"user_{user_id}"

        # Если это сам бот
        if user_id == bot.id:
            print(f"🤖 Бот добавлен в чат {chat_id}")
            # Даем боту время на инициализацию
            await asyncio.sleep(2)
            continue

        print(f"🆕 Новый участник: @{username} (ID: {user_id})")

        # Регистрируем пользователя с рейтингом 0
        registered = await register_user_if_not_exists(chat_id, user_id, username)

        if registered:
            # Даем небольшую задержку перед установкой префикса
            await asyncio.sleep(2)

            # Проверяем, является ли пользователь владельцем
            is_owner = False
            try:
                member_status = await bot.get_chat_member(chat_id, user_id)
                is_owner = member_status.status == 'creator'
            except Exception as e:
                print(f"DEBUG: Не удалось получить статус пользователя {user_id}: {e}")

            # Устанавливаем префикс
            prefix_success = await set_user_prefix(chat_id, user_id, 0, is_owner)

            if prefix_success:
                print(f"✅ Автоматически установлен префикс новому участнику @{username}")
            else:
                print(f"⚠️ Не удалось установить префикс новому участнику @{username}")

        # Небольшая задержка между обработкой участников
        await asyncio.sleep(1)

# ДОБАВЛЕНО: Обработчик для реакций на сообщения
@dp.message_reaction_handler()
async def handle_message_reaction(reaction_update: MessageReactionUpdated):
    """Обрабатывает реакции на сообщения"""
    chat_id = reaction_update.chat.id

    print(f"🎯 Обновление реакции в чате {chat_id}")

    # Проверяем новую реакцию
    if reaction_update.new_reaction:
        # Проверяем, есть ли реакция 🤝
        has_handshake = False

        for reaction in reaction_update.new_reaction:
            if hasattr(reaction, 'emoji'):
                if hasattr(reaction.emoji, 'emoji'):
                    # Это обычный эмодзи (ReactionTypeEmoji)
                    if reaction.emoji.emoji == HANDSHAKE_EMOJI:
                        has_handshake = True
                        break
                elif isinstance(reaction.emoji, str):
                    # Это строковый эмодзи
                    if reaction.emoji == HANDSHAKE_EMOJI:
                        has_handshake = True
                        break

        if has_handshake:
            print(f"🎯 Найдена реакция 🤝 в чате {chat_id}")

            try:
                # Получаем информацию о сообщении, на которое поставили реакцию
                message = await bot.get_message(chat_id, reaction_update.message_id)

                # Получаем ID автора сообщения
                target_user_id = message.from_user.id
                target_username = message.from_user.username or message.from_user.first_name or f"user_{target_user_id}"

                # ID пользователя, который поставил реакцию
                reactor_id = reaction_update.user.id

                # Проверяем, чтобы пользователь не начислял баллы сам себе
                if target_user_id == reactor_id:
                    print(f"⚠️ Пользователь {target_user_id} пытается начислить баллы сам себе")
                    return

                print(f"🔄 Обработка реакции 🤝: {reactor_id} → {target_user_id}")

                # Используем ту же систему обработки что и для благодарностей
                success = await add_thank_to_queue(
                    chat_id=chat_id,
                    sender_id=reactor_id,
                    target_user_id=target_user_id,
                    target_username=target_username,
                    message_id=reaction_update.message_id,
                    reaction=True
                )

                if success:
                    print(f"✅ Балл за реакцию 🤝 успешно начислен")
                else:
                    print(f"❌ Ошибка при начислении балла за реакцию")

            except Exception as e:
                print(f"❌ Ошибка при обработке реакции: {e}")
                import traceback
                traceback.print_exc()

@dp.message_handler(lambda message: message.chat.type == 'private')
async def block_private_messages(message: types.Message):
    print(f"BLOCKED: Private message from {message.from_user.id}: {message.text}")
    return

async def is_creator(user_id):
    return user_id == CREATOR_ID

# НОВЫЙ УЛУЧШЕННЫЙ ОБРАБОТЧИК БЛАГОДАРНОСТЕЙ
@dp.message_handler(lambda message: message.text and not message.text.startswith('/') and message.reply_to_message)
async def check_thank_message(message: types.Message):
    """Обработчик благодарностей с гарантированной обработкой"""
    if message.chat.type == 'private':
        return

    # Быстрая проверка
    if not message.text or not message.text.strip():
        return

    if not message.reply_to_message:
        return

    # Логируем входящее сообщение
    print(f"📥 Получено сообщение от {message.from_user.id} в чате {message.chat.id}")
    print(f"📝 Текст: '{message.text[:50]}...'")

    # ИЗМЕНЕНО: Убрана проверка кулдауна, теперь всегда можно благодарить
    # Просто проверяем наличие слов благодарности
    if not contains_thank_word(message.text):
        return

    # Получаем информацию о целевом пользователе
    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

    print(f"🎯 Начинаю обработку благодарности: {message.from_user.id} → {target_user_id}")

    # Добавляем в очередь на обработку
    try:
        success = await add_thank_to_queue(
            chat_id=message.chat.id,
            sender_id=message.from_user.id,
            target_user_id=target_user_id,
            target_username=target_username,
            message_id=message.message_id
        )

        if success:
            print(f"✅ Благодарность добавлена в очередь успешно")
        else:
            print(f"❌ Ошибка при добавлении в очередь")

    except Exception as e:
        print(f"🔥 КРИТИЧЕСКАЯ ОШИБКА в обработчике: {e}")
        import traceback
        traceback.print_exc()

@dp.message_handler(commands=["help", "start"])
async def help_command(message: types.Message):
    if message.chat.type == 'private':
        return

    creator_info = f"\n👑 Создатель бота: ID {CREATOR_ID}"

    help_text = f"""🎯 ДОСТУПНЫЕ КОМАНДЫ:

➕ Добавление баллов:
/add или /plus - добавить балл участнику (ответом на его сообщение)
/plus 10 за хорошее поведение - добавить 10 баллов (ответом на сообщение, только создатель)*
/minus 5 за опоздание - вычесть 5 баллов (ответом на сообщение, только создатель)*

📊 Информация:
/my - мой профиль (баллы и статус) - удаляется через 10 секунд
/top - ТОП-5 участников чата - удаляется через 60 секунд
/info - информация о системе репутации - удаляется через 60 секунд

⚙️ Админ-команды:
/update - обновить префиксы ВСЕХ участников (только создатель)*

🤖 Автоматически:
• При входе в группу участник автоматически получает префикс ★☆☆ [0]
• Баллы добавляются при словах: спасибо, благодарю, спс, саул, от души, мерси, спасибки и др.
• Баллы добавляются за реакцию 🤝 (рукопожатие) на сообщение
✅ +1 балл за благодарность удаляется через 10 секунд

⭐ ФОРМАТ ПРЕФИКСОВ:
• ★☆☆ [0-14]
• ★★☆ [15-29]
• ★★★ [30+]

⚠️ ВАЖНО О ПРЕФИКСАХ:
• Бот автоматически делает пользователей администраторами при начислении баллов
• Все административные права отключены (только префикс отображается)
• Префикс обновляется при каждом начислении баллов
• Бот должен быть администратором с правом назначать администраторов

📝 *Примечание: Команды /plus и /minus работают ТОЛЬКО как ответ на сообщение.
   Формат: /plus 10 за хорошее поведение
   Формат: /minus 5 за опоздание{creator_info}"""

    msg = await message.reply(help_text)
    asyncio.create_task(delete_command_with_delay(message, msg, 60))

@dp.message_handler(commands=["info"])
async def info(message: types.Message):
    if message.chat.type == 'private':
        return

    info_text = f"""🌟 СИСТЕМА РЕПУТАЦИИ

📊 Уровни статусов:
★☆☆ [0-14] - Начинающий
★★☆ [15-29] - Профессионал
★★★ [30+] - Элита

🎯 Как получать баллы:
1. Ответьте /add на полезное сообщение
2. Поблагодарите участника словами: спасибо, благодарю, спс, саул, от души, мерси, спасибки
3. Поставьте реакцию 🤝 (рукопожатие) на сообщение участника
4. Получайте благодарности и реакции от других участников
5. Создатель может добавлять баллы командой /plus (ответом на сообщение)

⏰ Время удаления сообщений:
• /info и /top - удаляются через 60 секунд
• /my - удаляется через 10 секунд
• +1 балл за благодарность - удаляется через 10 секунд
• Команды /plus и /minus - удаляются через 30 секунд

🤖 АВТОМАТИЧЕСКИ:
• Новые участники автоматически получают префикс ★☆☆ [0]
• Префикс обновляется при каждом изменении баллов
• Бот сам сделает вас администратором при начислении баллов
• Благодарить и ставить реакции можно без ограничений!

🎉 При повышении ранга все участники увидят праздничное уведомление! 🎉

👑 Создатель: ID {CREATOR_ID}"""

    msg = await message.reply(info_text)
    asyncio.create_task(delete_command_with_delay(message, msg, 60))

@dp.message_handler(commands=["add", "pa", "добавить"])
async def add_points(message: types.Message):
    if message.chat.type == 'private':
        return

    if not message.reply_to_message:
        msg = await message.reply("↩️ Ответьте этой командой на сообщение участника, чтобы добавить ему балл.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

    # Используем ту же систему обработки что и для благодарностей
    print(f"🔄 Обработка команды /add для {target_user_id}")

    success = await add_thank_to_queue(
        chat_id=message.chat.id,
        sender_id=message.from_user.id,
        target_user_id=target_user_id,
        target_username=target_username,
        message_id=message.message_id
    )

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

@dp.message_handler(commands=["plus"])
async def plus_points(message: types.Message):
    if message.chat.type == 'private':
        return

    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /plus")
        msg = await message.reply("❌ Эта команда доступна только создателю бота!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    if not message.reply_to_message:
        help_text = """➕ Добавление баллов пользователю (только создатель):

Эта команда работает ТОЛЬКО как ответ на сообщение!

Формат:
/plus 10 за хорошее поведение
/plus 5 за помощь
/plus 20 за отличную работу

Пример:
1. Ответьте на сообщение пользователя
2. Напишите: /plus 10 за активность
3. Пользователь получит 10 баллов

⚠️ Важно: Команда работает только как ответ на сообщение!"""

        msg = await message.reply(help_text)
        asyncio.create_task(delete_command_with_delay(message, msg, 15))
        return

    # Извлекаем баллы и причину из команды
    points, reason = extract_points_from_command(message.text)

    if points <= 0:
        msg = await message.reply("❌ Неверный формат. Используйте: /plus N причина\nПример: /plus 10 за хорошее поведение")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    if points > 1000:
        msg = await message.reply("⚠️ Слишком много баллов за раз. Максимум 1000 за одну операцию.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    success, result_msg = await change_user_points_by_reply(message, points, is_addition=True, reason=reason)

    msg = await message.reply(result_msg)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["minus"])
async def minus_points(message: types.Message):
    if message.chat.type == 'private':
        return

    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /minus")
        msg = await message.reply("❌ Эта команда доступна только создателю бota!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    if not message.reply_to_message:
        help_text = """➖ Вычитание баллов у пользователя (только создатель):

Эта команда работает ТОЛЬКО как ответ на сообщение!

Формат:
/minus 10 за плохое поведение
/minus 5 за опоздание
/minus 20 за нарушение правил

Пример:
1. Ответьте на сообщение пользователя
2. Напишите: /minus 5 за опоздание
3. У пользователя вычтут 5 баллов

⚠️ Важно: Команда работает только как ответ на сообщение!"""

        msg = await message.reply(help_text)
        asyncio.create_task(delete_command_with_delay(message, msg, 15))
        return

    # Извлекаем баллы и причину из команды
    points, reason = extract_points_from_command(message.text)

    if points <= 0:
        msg = await message.reply("❌ Неверный формат. Используйте: /minus N причина\nПример: /minus 10 за плохое поведение")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    if points > 1000:
        msg = await message.reply("⚠️ Слишком много баллов за раз. Максимум 1000 за одну операцию.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    success, result_msg = await change_user_points_by_reply(message, points, is_addition=False, reason=reason)

    msg = await message.reply(result_msg)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["my", "me", "profile"])
async def my_profile(message: types.Message):
    if message.chat.type == 'private':
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or f"user_{user_id}"

    # АВТОМАТИЧЕСКАЯ РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ, ЕСЛИ ЕГО НЕТ В БАЗЕ
    await register_user_if_not_exists(chat_id, user_id, username)

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
            next_level = "★★☆"
            points_to_next = 15 - user_balance
        elif user_balance < 30:
            next_level = "★★★"
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
        if user_balance < 15:
            progress = user_balance / 15 * 100
        elif user_balance < 30:
            progress = (user_balance - 15) / 15 * 100
        else:
            progress = 100

        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        profile_text += f"📊 Прогресс: [{progress_bar}] {int(progress)}%\n"

    profile_text += "\n💡 Совет: Помогайте другим участникам\nи получайте благодарности для повышения репутации!"

    msg = await message.reply(profile_text)
    asyncio.create_task(delete_command_with_delay(message, msg, 10))  # 10 секунд для /my

@dp.message_handler(commands=["top", "рейтинг", "лидеры"])
async def top_players(message: types.Message):
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

    # Подсчитываем пользователей с 0 баллами
    zero_points_players = sum(1 for user_data in chat_points.values() if user_data['points'] == 0)

    top_text += f"📊 Статистика:\n• Всего участников: {total_players}\n• С 0 баллами: {zero_points_players}\n\n"
    top_text += f"💡 Новые участники автоматически получают префикс ★☆☆ [0]"

    msg = await message.reply(top_text, parse_mode="HTML")
    asyncio.create_task(delete_command_with_delay(message, msg, 60))  # 60 секунд для /top

# ИЗМЕНЕНО: Команда /update теперь регистрирует всех участников и обновляет префиксы
@dp.message_handler(commands=["update", "u"])
async def update_prefix(message: types.Message):
    if message.chat.type == 'private':
        return

    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /update")
        msg = await message.reply("❌ Эта команда доступна только создателю бота!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    chat_id = message.chat.id

    # Отправляем сообщение о начале обновления
    status_msg = await message.reply("🔄 Начинаю обновление префиксов всех участников...")

    try:
        # Сначала регистрируем всех участников чата
        registered = await register_all_chat_members(chat_id)

        # Загружаем данные чата
        chat_points = load_chat_data(chat_id)

        if not chat_points:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text="❌ В чате нет зарегистрированных участников"
            )
            asyncio.create_task(delete_command_with_delay(message, status_msg, 10))
            return

        print(f"🔄 Обновляю префиксы для чата {chat_id} ({len(chat_points)} пользователей)")

        updated_count = 0
        failed_count = 0

        # Обновляем префиксы для каждого пользователя
        for user_id, user_data in chat_points.items():
            try:
                points = user_data["points"]

                # Проверяем, является ли пользователь владельцем
                is_owner = False
                try:
                    member_status = await bot.get_chat_member(chat_id, user_id)
                    is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
                except Exception as e:
                    print(f"DEBUG: Не удалось получить статус пользователя {user_id}: {e}")

                # Обновляем префикс
                prefix_success = await set_user_prefix(chat_id, user_id, points, is_owner)
                if prefix_success:
                    updated_count += 1
                    print(f"✅ Префикс обновлен для пользователя {user_id}")
                else:
                    failed_count += 1
                    print(f"⚠️ Не удалось обновить префикс для пользователя {user_id}")

                # Обновляем статус каждые 5 пользователей
                if (updated_count + failed_count) % 5 == 0:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg.message_id,
                        text=f"🔄 Обновление префиксов...\nОбработано: {updated_count + failed_count}/{len(chat_points)}\nУспешно: {updated_count}, Неудачно: {failed_count}"
                    )

                await asyncio.sleep(0.5)  # Небольшая задержка чтобы не спамить API

            except Exception as e:
                failed_count += 1
                print(f"❌ Ошибка при обновлении префикса для пользователя {user_id}: {e}")

        # Финальное сообщение
        result_text = f"""✅ Обновление префиксов завершено!

📊 Статистика:
👥 Всего участников: {len(chat_points)}
✅ Успешно обновлено: {updated_count}
❌ Не удалось обновить: {failed_count}
➕ Зарегистрировано новых: {registered}

💡 Не удачные обновления обычно происходят из-за:
1. Бот не имеет прав администратора
2. Пользователь заблокировал бота
3. Пользователь вышел из чата"""

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=result_text
        )

        # Удаляем сообщения через 30 секунд
        asyncio.create_task(delete_command_with_delay(message, status_msg, 30))

    except Exception as e:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ Ошибка при обновлении префиксов: {str(e)[:100]}..."
        )
        asyncio.create_task(delete_command_with_delay(message, status_msg, 10))

@dp.message_handler()
async def catch_all_messages(message: types.Message):
    if message.chat.type == 'private':
        print(f"BLOCKED: Private message from {message.from_user.id}")
        return
    print(f"DEBUG: Message in chat {message.chat.id} from {message.from_user.id}")

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН С ОБНОВЛЁННОЙ СИСТЕМОЙ РЕПУТАЦИИ!")
    print("=" * 60)
    print(f"\n👑 СОЗДАТЕЛЬ БОТА: ID {CREATOR_ID}")
    print("\n🌟 СИСТЕМА СТАТУСОВ:")
    print("   ★☆☆ [0-14]")
    print("   ★★☆ [15-29]")
    print("   ★★★ [30+]")
    print("\n⏰ ВРЕМЯ УДАЛЕНИЯ СООБЩЕНИЙ:")
    print("   • /info и /top - 60 секунд")
    print("   • /my - 10 секунд")
    print("   • +1 балл за благодарность - 10 секунд")
    print("   • Команды /plus и /minus - 30 секунд")
    print("\n🤖 АВТОМАТИЧЕСКИЕ ФУНКЦИИ:")
    print("   • Новые участники получают префикс ★☆☆ [0]")
    print("   • Автоматическая регистрация при первом взаимодействии")
    print("   • Обновление префиксов при запуске бота")
    print("   • Благодарить и ставить реакции можно без ограничений!")
    print(f"   • Реакция {HANDSHAKE_EMOJI} добавляет +1 балл")
    print("\n🔧 УЛУЧШЕНИЯ:")
    print("   • Гарантированная обработка всех благодарностей и реакций")
    print("   • Система очередей для предотвращения пропусков")
    print("   • Улучшенное логирование")
    print("\n🎯 ДОСТУПНЫЕ КОМАНДЫ ДЛЯ ВСЕХ:")
    print("   /help - все команды")
    print("   /my - мой профиль (удаляется через 10 секунд)")
    print("   /top - топ-5 участников (удаляется через 60 секунд)")
    print("   /add - добавить балл (ответом на сообщение)")
    print("   /info - о системе (удаляется через 60 секунд)")
    print("\n🔐 ЗАЩИЩЕННЫЕ КОМАНДЫ (ТОЛЬКО СОЗДАТЕЛЬ):")
    print(f"   /plus N причина - добавить N баллов (создатель: {CREATOR_ID})")
    print(f"   /minus N причина - вычесть N баллов (создатель: {CREATOR_ID})")
    print(f"   /update - обновить префиксы всех участников (создатель: {CREATOR_ID})")
    print("\n⚠️ ВАЖНО О КОМАНДАХ /PLUS И /MINUS:")
    print("   • Работают ТОЛЬКО как ответ на сообщение")
    print("   • Формат: /plus 10 за хорошее поведение")
    print("   • Формат: /minus 5 за опоздание")
    print("\n🔄 ПРИ ЗАПУСКЕ БОТА:")
    print("   1. Обновляются все префиксы участников")
    print("   2. Отправляется уведомление о перезапуске во все чаты")
    print("   3. Уведомление удаляется через 10 секунд")
    print("\n💬 Автоматическое повышение при:")
    print(f"   • Словах благодарности: {', '.join(THANK_WORDS[:6])}...")
    print(f"   • Реакции: {HANDSHAKE_EMOJI} (рукопожатие)")
    print("=" * 60)

    # Запускаем обновление префиксов и отправку уведомлений при старте
    async def on_startup(dp):
        await update_all_prefixes_on_start()
        await send_restart_notification()

    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)