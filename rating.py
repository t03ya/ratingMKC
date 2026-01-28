import os
import json
import asyncio
import time
import re
import glob
import threading
from datetime import datetime, timedelta
# aiogram==2.25.1
from aiogram.utils import executor
from aiogram import Bot, Dispatcher, types
from aiogram.types import ChatAdministratorRights
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# ДОБАВЛЕНО: Словарь для блокировок файлов
file_locks = {}
file_lock_lock = threading.Lock()  # Блокировка для управления блокировками файлов

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

# Время между благодарностями (5 минут в секундах)
THANK_COOLDOWN = 300  # 5 минут

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

# ИЗМЕНЕНО: Функции загрузки и сохранения с блокировками
def load_chat_data(chat_id):
    """Загружает данные для конкретного чата с блокировкой"""
    points_file = get_points_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if points_file not in file_locks:
            file_locks[points_file] = threading.Lock()

    lock = file_locks[points_file]

    with lock:
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
    """Сохраняет данные для конкретного чата с блокировкой"""
    points_file = get_points_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if points_file not in file_locks:
            file_locks[points_file] = threading.Lock()

    lock = file_locks[points_file]

    with lock:
        try:
            with open(points_file, "w", encoding="utf-8") as f:
                data_to_save = {str(k): v for k, v in data.items()}
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ERROR saving chat data: {e}")

def load_last_thanks(chat_id):
    """Загружает время последних благодарностей для чата с блокировкой"""
    thank_file = get_thank_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if thank_file not in file_locks:
            file_locks[thank_file] = threading.Lock()

    lock = file_locks[thank_file]

    with lock:
        if os.path.exists(thank_file):
            try:
                with open(thank_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {int(k): float(v) for k, v in data.items()}
            except Exception as e:
                print(f"ERROR loading last thanks: {e}")
        return {}

def save_last_thanks(chat_id, data):
    """Сохраняет время последних благодарностей для чата с блокировкой"""
    thank_file = get_thank_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if thank_file not in file_locks:
            file_locks[thank_file] = threading.Lock()

    lock = file_locks[thank_file]

    with lock:
        try:
            with open(thank_file, "w", encoding="utf-8") as f:
                data_to_save = {str(k): v for k, v in data.items()}
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ERROR saving last thanks: {e}")

def load_last_ranks(chat_id):
    """Загружает последние ранги для чата с блокировкой"""
    rank_file = get_rank_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if rank_file not in file_locks:
            file_locks[rank_file] = threading.Lock()

    lock = file_locks[rank_file]

    with lock:
        if os.path.exists(rank_file):
            try:
                with open(rank_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            except Exception as e:
                print(f"ERROR loading last ranks: {e}")
        return {}

def save_last_ranks(chat_id, data):
    """Сохраняет последние ранги для чата с блокировкой"""
    rank_file = get_rank_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if rank_file not in file_locks:
            file_locks[rank_file] = threading.Lock()

    lock = file_locks[rank_file]

    with lock:
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

# ИЗМЕНЕНО: Унифицированная функция для атомарной проверки и обновления кулдауна
def can_thank_now(chat_id, user_id):
    """Проверяет, можно ли пользователю отправить благодарность (атомарная операция)"""
    thank_file = get_thank_file(chat_id)

    # Получаем блокировку для этого файла
    with file_lock_lock:
        if thank_file not in file_locks:
            file_locks[thank_file] = threading.Lock()

    lock = file_locks[thank_file]

    with lock:
        # Загружаем данные с блокировкой
        if os.path.exists(thank_file):
            try:
                with open(thank_file, "r", encoding="utf-8") as f:
                    thanks_data = json.load(f)
                    thanks_data = {int(k): float(v) for k, v in thanks_data.items()}
            except:
                thanks_data = {}
        else:
            thanks_data = {}

        current_time = time.time()

        if user_id in thanks_data:
            last_time = thanks_data[user_id]
            if current_time - last_time < THANK_COOLDOWN:
                return False, THANK_COOLDOWN - int(current_time - last_time)

        # Обновляем время сразу же
        thanks_data[user_id] = current_time

        try:
            with open(thank_file, "w", encoding="utf-8") as f:
                data_to_save = {str(k): v for k, v in thanks_data.items()}
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ERROR saving last thanks in can_thank_now: {e}")
            return False, 0

        return True, 0

# ИЗМЕНЕНО: Удалена функция update_last_thank, так как теперь обновление происходит в can_thank_now

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
        print(f"DEBUG: Ищу пользователя с username '{username}' в чате {chat_id}")

        chat_points = load_chat_data(chat_id)

        for user_id, user_data in chat_points.items():
            user_username = user_data.get('username', '').lstrip('@')
            if user_username and user_username.lower() == username.lower():
                print(f"DEBUG: Нашел пользователя {user_id} по username в сохраненных данных")
                return user_id

        print(f"DEBUG: Пользователь @{username} не найден в сохраненных данных")
        return None

    except Exception as e:
        print(f"ERROR: Не удалось найти пользователя @{username_input}: {e}")
        return None

async def make_user_admin_for_prefix(chat_id, user_id):
    """Делает пользователя администратором с минимальными правами для установки префикса"""
    try:
        print(f"DEBUG: Пытаюсь сделать пользователя {user_id} администратором в чате {chat_id}")

        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            current_status = member_status.status
            print(f"DEBUG: Текущий статус пользователя {user_id}: {current_status}")

            if current_status in ['administrator', 'creator']:
                print(f"DEBUG: Пользователь {user_id} уже администратор")
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
                print(f"SUCCESS: Пользователь {user_id} успешно назначен администратором")
                await asyncio.sleep(2)
                return True
            else:
                print(f"ERROR: Не удалось назначить пользователя {user_id} администратором")
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

        print(f"DEBUG: Устанавливаю префикс '{prefix}' для пользователя {user_id}")

        # Проверяем статус пользователя
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            user_is_admin = member_status.status in ['administrator', 'creator']
            current_status = member_status.status

            print(f"DEBUG: Статус пользователя {user_id}: {current_status}, админ: {user_is_admin}")

            if not user_is_admin:
                print(f"DEBUG: Пользователь {user_id} не администратор, пытаюсь сделать админом...")
                admin_success = await make_user_admin_for_prefix(chat_id, user_id)
                if not admin_success:
                    print(f"ERROR: Не удалось сделать пользователя {user_id} администратором для префикса")
                    return False
                # Даем больше времени Telegram обработать
                await asyncio.sleep(3)

            # Теперь пробуем установить префикс
            # Ограничение Telegram: максимум 16 символов для префикса
            prefix_to_set = prefix[:16]

            print(f"DEBUG: Пробую установить префикс '{prefix_to_set}' для пользователя {user_id}")

            # Попробуем установить префикс несколько раз
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    await bot.set_chat_administrator_custom_title(
                        chat_id=chat_id,
                        user_id=user_id,
                        custom_title=prefix_to_set
                    )

                    print(f"SUCCESS: Префикс '{prefix_to_set}' установлен для пользователя {user_id}")
                    return True

                except Exception as e:
                    print(f"ERROR (попытка {attempt + 1}): Не удалось установить префикс: {e}")

                    # Если ошибка связана с правами, возможно у бота недостаточно прав
                    if "not enough rights" in str(e).lower() or "права" in str(e).lower():
                        print(f"ERROR: У бота недостаточно прав для установки префикса")
                        return False

                    if attempt < max_attempts - 1:
                        print(f"DEBUG: Жду 2 секунды перед следующей попыткой...")
                        await asyncio.sleep(2)
                    else:
                        print(f"ERROR: Все попытки установить префикс провалились")
                        return False

        except Exception as e:
            print(f"DEBUG: Ошибка при проверке статуса: {e}")
            return False

    except Exception as e:
        print(f"ERROR: Критическая ошибка при установке префикса: {e}")
        return False

async def change_user_points_by_reply(message, points_change, is_addition=True, reason=""):
    """Изменяет баллы пользователя в ответ на сообщение и обновляет префикс"""
    chat_id = message.chat.id

    if not message.reply_to_message:
        return False, "❌ Эта команда должна быть отправлена в ответ на сообщение пользователя!"

    target_user_id = message.reply_to_message.from_user.id
    target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

    # ИЗМЕНЕНО: Атомарная операция изменения баллов
    points_file = get_points_file(chat_id)
    rank_file = get_rank_file(chat_id)

    # Получаем блокировки для всех файлов
    with file_lock_lock:
        for file_path in [points_file, rank_file]:
            if file_path not in file_locks:
                file_locks[file_path] = threading.Lock()

    # Используем блокировку для points_file, так как это основной файл
    lock = file_locks[points_file]

    with lock:
        # Загружаем данные
        if os.path.exists(points_file):
            try:
                with open(points_file, "r", encoding="utf-8") as f:
                    chat_points = json.load(f)
                    chat_points = {int(k): v for k, v in chat_points.items()}
            except:
                chat_points = {}
        else:
            chat_points = {}

        # Загружаем ранги
        if os.path.exists(rank_file):
            try:
                with open(rank_file, "r", encoding="utf-8") as f:
                    chat_last_ranks = json.load(f)
                    chat_last_ranks = {int(k): v for k, v in chat_last_ranks.items()}
            except:
                chat_last_ranks = {}
        else:
            chat_last_ranks = {}

        if target_user_id not in chat_points:
            try:
                member = await bot.get_chat_member(chat_id, target_user_id)
                current_username = member.user.username or member.user.first_name or f"user_{target_user_id}"

                if is_addition:
                    chat_points[target_user_id] = {"username": current_username, "points": points_change}
                    old_points = 0
                    new_points = points_change
                    action_word = "добавлено"
                else:
                    return False, f"❌ Пользователь @{target_username} еще не имеет баллов"
            except Exception as e:
                print(f"ERROR: Не удалось получить информацию о пользователе {target_user_id}: {e}")
                return False, f"❌ Ошибка при получении информации о пользователе"
        else:
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

        new_level = get_level(new_points) if target_user_id in chat_points else "BASIC"

        # Сохраняем данные
        with open(points_file, "w", encoding="utf-8") as f:
            data_to_save = {str(k): v for k, v in chat_points.items()}
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)

        rank_change = ""
        if 'old_level' in locals() and old_level != new_level and not is_owner:
            rank_change = f"\n🎉 Изменение ранга: {old_level} → {new_level}"
            chat_last_ranks[target_user_id] = new_level

            # Сохраняем ранги с их блокировкой
            with file_locks[rank_file]:
                with open(rank_file, "w", encoding="utf-8") as f:
                    data_to_save = {str(k): v for k, v in chat_last_ranks.items()}
                    json.dump(data_to_save, f, ensure_ascii=False, indent=4)

    # Устанавливаем префикс (это делаем вне блокировки, так как это сетевой запрос)
    prefix_success = await set_user_prefix(chat_id, target_user_id, new_points, is_owner)

    if prefix_success:
        prefix_msg = "✅ Префикс обновлен"
    else:
        prefix_msg = "⚠️ Не удалось установить префикс (проверьте права бота)"

    old_points_display = old_points if 'old_points' in locals() else 0

    # Формируем сообщение с причиной
    reason_text = f"\n📝 Причина: {reason}" if reason else ""

    result_msg = f"""✅ Успешно! {action_word} {points_change} баллов.

👤 Пользователь: @{target_username}
📊 Было: {old_points_display} | Стало: {new_points}
⭐ Новый статус: {get_rank_display(new_points, is_owner)}
{prefix_msg}{rank_change}{reason_text}"""

    return True, result_msg

print("\n" + "="*50)
print("🌟 СИСТЕМА СТАТУСОВ:")
print("★☆☆ [0-14]")
print("★★☆ [15-29]")
print("★★★ [30+]")
print("="*50 + "\n")

# ИЗМЕНЕНО: Улучшенная функция для автоматического добавления баллов
async def add_points_automatically(message, target_user_id, target_username):
    """Функция для автоматического добавления баллов с атомарными операциями"""
    chat_id = message.chat.id

    points_file = get_points_file(chat_id)
    rank_file = get_rank_file(chat_id)

    # Получаем блокировки для всех файлов
    with file_lock_lock:
        for file_path in [points_file, rank_file]:
            if file_path not in file_locks:
                file_locks[file_path] = threading.Lock()

    # Используем блокировку для points_file
    lock = file_locks[points_file]

    rank_up = False
    old_level = None
    new_points = None
    is_owner = False

    with lock:
        # Загружаем данные
        if os.path.exists(points_file):
            try:
                with open(points_file, "r", encoding="utf-8") as f:
                    chat_points = json.load(f)
                    chat_points = {int(k): v for k, v in chat_points.items()}
            except:
                chat_points = {}
        else:
            chat_points = {}

        # Загружаем ранги
        if os.path.exists(rank_file):
            try:
                with open(rank_file, "r", encoding="utf-8") as f:
                    chat_last_ranks = json.load(f)
                    chat_last_ranks = {int(k): v for k, v in chat_last_ranks.items()}
            except:
                chat_last_ranks = {}
        else:
            chat_last_ranks = {}

        if target_user_id in chat_points:
            old_points = chat_points[target_user_id]["points"]
            chat_points[target_user_id]["points"] += 1
            old_level = get_level(old_points)

            if chat_points[target_user_id]["username"] != target_username:
                chat_points[target_user_id]["username"] = target_username
        else:
            chat_points[target_user_id] = {"username": target_username, "points": 1}
            old_points = 0
            old_level = "BASIC"

        try:
            member_status = await bot.get_chat_member(chat_id, target_user_id)
            is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
            print(f"DEBUG: Статус пользователя {target_user_id}: {member_status.status}, is_owner: {is_owner}")
        except Exception as e:
            print(f"WARNING: Could not get member status: {e}")

        new_points = chat_points[target_user_id]["points"]
        new_level = get_level(new_points)

        print(f"DEBUG: Начисляю балл пользователю {target_user_id}. Было: {old_points}, стало: {new_points}")

        # Сохраняем данные
        with open(points_file, "w", encoding="utf-8") as f:
            data_to_save = {str(k): v for k, v in chat_points.items()}
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)

        if old_level != new_level and not is_owner:
            rank_up = True
            chat_last_ranks[target_user_id] = new_level

            # Сохраняем ранги с их блокировкой
            with file_locks[rank_file]:
                with open(rank_file, "w", encoding="utf-8") as f:
                    data_to_save = {str(k): v for k, v in chat_last_ranks.items()}
                    json.dump(data_to_save, f, ensure_ascii=False, indent=4)

    # Пытаемся установить префикс (делаем вне блокировки)
    prefix_success = False
    if not is_owner:
        prefix_success = await set_user_prefix(chat_id, target_user_id, new_points, is_owner)

        if prefix_success:
            print(f"SUCCESS: Префикс обновлен для {target_user_id} -> {get_rank_for_title(new_points, is_owner)}")
        else:
            print(f"WARNING: Не удалось обновить префикс для {target_user_id}")
    else:
        print(f"DEBUG: Пользователь {target_user_id} владелец, префикс не обновляем")

    user_type = "OWNER" if is_owner else "USER"
    print(f"STATUS UPDATE [{user_type}] in chat {chat_id}: @{target_username} is now {get_rank_for_title(new_points, is_owner)}")

    return True, old_level if not rank_up else new_level

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

@dp.message_handler(lambda message: message.chat.type == 'private')
async def block_private_messages(message: types.Message):
    print(f"BLOCKED: Private message from {message.from_user.id}: {message.text}")
    return

async def is_creator(user_id):
    return user_id == CREATOR_ID

# ИЗМЕНЕНО: Добавлен принудительный await для предотвращения блокировки
@dp.message_handler(lambda message: message.text and not message.text.startswith('/') and message.reply_to_message)
async def check_thank_message(message: types.Message):
    if message.chat.type == 'private':
        return

    print(f"DEBUG: Проверяю сообщение в чате {message.chat.id} от {message.from_user.id}")

    # ИЗМЕНЕНО: Добавлен await для предотвращения блокировки при высокой нагрузке
    await asyncio.sleep(0.01)  # Небольшая задержка для снижения нагрузки

    can_thank, wait_time = can_thank_now(message.chat.id, message.from_user.id)

    if not can_thank:
        print(f"DEBUG: Кулдаун для {message.from_user.id}. Осталось ждать: {wait_time} сек")
        return

    if message.text and contains_thank_word(message.text):
        target_user_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name or f"user_{target_user_id}"

        print(f"DEBUG: Найдено слово благодарности, добавляем балл для {target_user_id}")

        success, old_rank = await add_points_automatically(message, target_user_id, target_username)

        if success:
            thank_msg = "✅ +1 балл за благодарность!"
            msg = await message.reply(thank_msg)
            # Удаляем через 10 секунд как указано в требованиях
            await asyncio.sleep(10)
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
/update @username - обновить префикс пользователя (только создатель)*
/update 123456789 - обновить префикс по ID (только создатель)

🤖 Автоматически:
Баллы добавляются при словах: спасибо, благодарю, спс, саул, от души, мерси, спасибки и др.
⚠️ Благодарить можно не чаще 1 раза в 5 минут
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
   Формат: /minus 5 за плохое поведение{creator_info}"""

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
3. Получайте благодарности от других участников
4. Создатель может добавлять баллы командой /plus (ответом на сообщение)

⏰ Время удаления сообщений:
• /info и /top - удаляются через 60 секунд
• /my - удаляется через 10 секунд
• +1 балл за благодарность - удаляется через 10 секунд
• Команды /plus и /minus - удаляются через 30 секунд

⏱️ Правила:
• Благодарить можно не чаще 1 раза в 5 минут
• При повышении ранга все участники увидят праздничное уведомление! 🎉

📈 Автоматические действия:
• При начислении баллов бот сделает вас администратором (без прав)
• Ваш статус будет отображаться в префиксе: ★☆☆ [8]
• Префикс обновляется автоматически при каждом изменении баллов

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
    top_text += f"📊 Статистика: {total_players} участников в системе"

    msg = await message.reply(top_text, parse_mode="HTML")
    asyncio.create_task(delete_command_with_delay(message, msg, 60))  # 60 секунд для /top

@dp.message_handler(commands=["update", "u"])
async def update_prefix(message: types.Message):
    if message.chat.type == 'private':
        return

    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /update")
        msg = await message.reply("❌ Эта команда доступна только создателю бота!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return

    command_args = message.get_args().strip()

    if not command_args:
        help_text = """⚙️ Обновление префикса пользователя (только создатель):

/update @username - обновить префикс пользователя (можно тегнуть)
/update 123456789 - обновить префикс по ID

Примеры:
/update @ulia - обновить префикс для @ulia
/update 123456789 - обновить префикс для пользователя с ID 123456789

⚠️ Важно: Команда с @username работает только если пользователь уже получал баллы в этом чате."""

        msg = await message.reply(help_text)
        asyncio.create_task(delete_command_with_delay(message, msg, 15))
        return

    chat_id = message.chat.id
    chat_points = load_chat_data(chat_id)

    target_user_id = None
    username = None

    if command_args.isdigit():
        target_user_id = int(command_args)
        if target_user_id in chat_points:
            username = chat_points[target_user_id].get('username', f"user_{target_user_id}")
        else:
            msg = await message.reply(f"❌ Пользователь с ID {target_user_id} не найден в системе этого чата.")
            asyncio.create_task(delete_command_with_delay(message, msg))
            return
    else:
        username_input = command_args.lstrip('@')

        found = False
        for user_id, user_data in chat_points.items():
            user_username = user_data.get('username', '').lstrip('@')
            if user_username and user_username.lower() == username_input.lower():
                target_user_id = user_id
                username = user_data.get('username', f"user_{user_id}")
                found = True
                break

        if not found:
            msg = await message.reply(f"""❌ Пользователь @{username_input} не найден в системе этого чата.

Возможные причины:
1. Пользователь еще не получал баллов в этом чате
2. Username был изменен

Как обновить префикс:
• Используйте команду /add (ответом на сообщение пользователя) чтобы добавить балл
• Узнайте ID пользователя и используйте: /update ID""")
            asyncio.create_task(delete_command_with_delay(message, msg))
            return

    user_data = chat_points[target_user_id]
    display_username = username or user_data.get('username', f"user_{target_user_id}")

    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        pass

    prefix = get_rank_for_title(user_data["points"], is_owner=is_owner)

    print(f"DEBUG: Обновляю префикс пользователя {target_user_id} (@{display_username}) на '{prefix}'")

    prefix_success = await set_user_prefix(chat_id, target_user_id, user_data["points"], is_owner)

    if prefix_success:
        success_msg = f"✅ Префикс '{prefix}' успешно установлен!"
    else:
        success_msg = f"❌ Не удалось установить префикс. Убедитесь, что бот администратор и имеет права на назначение администраторов."

    owner_text = " (владелец)" if is_owner else ""
    response = f"{success_msg}\n\n"
    response += f"👤 Пользователь: <a href='tg://user?id={target_user_id}'>{display_username}</a>{owner_text}\n"
    response += f"🆔 ID: {target_user_id}\n"
    response += f"⭐ Текущий статус: {prefix}"

    msg = await message.reply(response, parse_mode="HTML")
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler()
async def catch_all_messages(message: types.Message):
    if message.chat.type == 'private':
        print(f"BLOCKED: Private message from {message.from_user.id}")
        return
    print(f"DEBUG: Message in chat {message.chat.id} from {message.from_user.id}: {message.text}")

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
    print("\n🎯 ДОСТУПНЫЕ КОМАНДЫ ДЛЯ ВСЕХ:")
    print("   /help - все команды")
    print("   /my - мой профиль (удаляется через 10 секунд)")
    print("   /top - топ-5 участников (удаляется через 60 секунд)")
    print("   /add - добавить балл (ответом на сообщение)")
    print("   /info - о системе (удаляется через 60 секунд)")
    print("\n🔐 ЗАЩИЩЕННЫЕ КОМАНДЫ (ТОЛЬКО СОЗДАТЕЛЬ):")
    print(f"   /plus N причина - добавить N баллов (создатель: {CREATOR_ID})")
    print(f"   /minus N причина - вычесть N баллов (создатель: {CREATOR_ID})")
    print(f"   /update @username - обновить префикс (создатель: {CREATOR_ID})")
    print("\n⚠️ ВАЖНО О КОМАНДАХ /PLUS И /MINUS:")
    print("   • Работают ТОЛЬКО как ответ на сообщение")
    print("   • Формат: /plus 10 за хорошее поведение")
    print("   • Формат: /minus 5 за опоздание")
    print("\n🔄 ПРИ ЗАПУСКЕ БОТА:")
    print("   1. Обновляются все префиксы участников")
    print("   2. Отправляется уведомление о перезапуске во все чаты")
    print("   3. Уведомление удаляется через 10 секунд")
    print("\n🔒 ИСПРАВЛЕНА ПРОБЛЕМА С БЛАГОДАРНОСТЯМИ:")
    print("   • Добавлены блокировки файлов для предотвращения гонок")
    print("   • Атомарные операции чтения/записи")
    print("   • Исключены пропуски при высокой нагрузке")
    print("\n💬 Автоматическое повышение при словах:")
    print(f"   {', '.join(THANK_WORDS[:6])}...")
    print("=" * 60)

    # Запускаем обновление префиксов и отправку уведомлений при старте
    async def on_startup(dp):
        await update_all_prefixes_on_start()
        await send_restart_notification()


    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)