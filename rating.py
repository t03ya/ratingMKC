import os
import json
import asyncio
import time
import re
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
CREATOR_ID = 8331388910 # ID создателя (ваш ID) - ЗАЩИЩЕННЫЕ КОМАНДЫ
# CREATOR_ID = 1808806022 # MIT License

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

    while LANG != "ru" and LANG != "eng':
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

def extract_username_and_points(text):
    """Извлекает username и количество баллов из текста команды"""
    # Паттерны для извлечения username и баллов
    patterns = [
        r'@(\w+)\s+(\d+)',  # @username 10
        r'(\d+)\s+@(\w+)',  # 10 @username
        r'@([a-zA-Z0-9_]{5,32})\s+(\d+)',  # @username с подчеркиваниями
        r'(\d+)\s+@([a-zA-Z0-9_]{5,32})',  # 10 @username с подчеркиваниями
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if pattern.startswith('@'):
                return match.group(1), int(match.group(2))
            else:
                return match.group(2), int(match.group(1))
    
    return None, 0

async def get_user_id_from_mention(chat_id, username_input):
    """Получает ID пользователя по username - исправленная версия"""
    try:
        # Убираем @ если есть
        username = username_input.lstrip('@')
        print(f"DEBUG: Ищу пользователя с username '{username}' в чате {chat_id}")
        
        # Сначала ищем в сохраненных данных чата
        chat_points = load_chat_data(chat_id)
        
        # Ищем пользователя по username в сохраненных данных
        for user_id, user_data in chat_points.items():
            user_username = user_data.get('username', '').lstrip('@')
            if user_username and user_username.lower() == username.lower():
                print(f"DEBUG: Нашел пользователя {user_id} по username в сохраненных данных")
                return user_id
        
        # Если не нашли в данных, пытаемся через Telegram API
        # Но для этого нужно перебрать всех участников, что может быть долго
        # Вместо этого предлагаем использовать ID или ответ на сообщение
        
        print(f"DEBUG: Пользователь @{username} не найден в сохраненных данных")
        return None
            
    except Exception as e:
        print(f"ERROR: Не удалось найти пользователя @{username_input}: {e}")
        return None

async def find_user_in_chat_by_username(chat_id, username):
    """Пытается найти пользователя в чате по username (альтернативный метод)"""
    # Этот метод может быть медленным для больших чатов
    # Лучше использовать ID или ответ на сообщение
    print(f"WARNING: Поиск по username может быть медленным. Рекомендуется использовать ID или ответ на сообщение.")
    return None

async def change_user_points(message, target_username, points_change, is_addition=True):
    """Изменяет баллы пользователя и обновляет префикс"""
    chat_id = message.chat.id
    
    # Получаем ID пользователя по username
    user_id = await get_user_id_from_mention(chat_id, target_username)
    
    if not user_id:
        # Пользователь не найден в сохраненных данных
        # Предлагаем альтернативные варианты
        error_msg = f"""❌ Пользователь @{target_username} не найден в системе этого чата.

Возможные причины:
1. Пользователь еще не получал баллов в этом чате
2. Username был изменен

Как добавить баллы:
• Используйте команду /add (ответом на сообщение пользователя)
• Узнайте ID пользователя и используйте: /update ID
• Попросите пользователя получить хотя бы 1 балл через благодарность"""
        
        return False, error_msg
    
    # Загружаем данные чата
    chat_points = load_chat_data(chat_id)
    chat_last_ranks = load_last_ranks(chat_id)
    
    # Проверяем, есть ли пользователь в данных чата
    if user_id not in chat_points:
        # Пользователь есть в поиске, но нет в данных - добавляем
        try:
            # Получаем актуальный username
            member = await bot.get_chat_member(chat_id, user_id)
            current_username = member.user.username or member.user.first_name or f"user_{user_id}"
            
            # Инициализируем пользователя
            if is_addition:
                chat_points[user_id] = {"username": current_username, "points": points_change}
                old_points = 0
                new_points = points_change
                action_word = "добавлено"
            else:
                # Нельзя вычитать у пользователя без баллов
                return False, f"❌ Пользователь @{target_username} еще не имеет баллов"
        except Exception as e:
            print(f"ERROR: Не удалось получить информацию о пользователе {user_id}: {e}")
            return False, f"❌ Ошибка при получении информации о пользователе @{target_username}"
    else:
        # Пользователь уже в системе - изменяем баллы
        old_points = chat_points[user_id]["points"]
        old_level = get_level(old_points)
        
        # Изменяем баллы
        if is_addition:
            new_points = old_points + points_change
            action_word = "добавлено"
        else:
            new_points = max(0, old_points - points_change)  # Не меньше 0
            action_word = "вычтено"
        
        chat_points[user_id]["points"] = new_points
    
    # Определяем, является ли пользователь владельцем
    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        pass
    
    new_level = get_level(new_points) if user_id in chat_points else "BASIC"
    
    # Устанавливаем/обновляем префикс
    if not is_owner:
        prefix_success = await set_user_prefix(chat_id, user_id, new_points, is_owner)
        
        if prefix_success:
            prefix_msg = "✅ Префикс обновлен"
        else:
            prefix_msg = "⚠️ Префикс не обновлен (проверьте права бота)"
    else:
        prefix_msg = "👑 Владелец - префикс не требуется"
    
    # Сохраняем данные
    save_chat_data(chat_id, chat_points)
    
    # Проверяем изменение ранга
    rank_change = ""
    if 'old_level' in locals() and old_level != new_level and not is_owner:
        rank_change = f"\n🎉 Изменение ранга: {old_level} → {new_level}"
        chat_last_ranks[user_id] = new_level
        save_last_ranks(chat_id, chat_last_ranks)
    
    # Формируем сообщение
    old_points_display = old_points if 'old_points' in locals() else 0
    result_msg = f"""✅ Успешно!
    
👤 Пользователь: @{target_username}
🆔 ID: {user_id}
📊 Баллов {action_word}: {points_change}
🏆 Было: {old_points_display} | Стало: {new_points}
⭐ Новый статус: {get_rank_display(new_points, is_owner)}
{prefix_msg}{rank_change}"""
    
    return True, result_msg

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
        
        # Сначала проверяем, не является ли пользователь уже администратором
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            current_status = member_status.status
            print(f"DEBUG: Текущий статус пользователя {user_id}: {current_status}")
            
            # Если уже админ или владелец, возвращаем успех
            if current_status in ['administrator', 'creator']:
                print(f"DEBUG: Пользователь {user_id} уже администратор")
                return True
        except Exception as e:
            print(f"DEBUG: Ошибка при получении статуса: {e}")
        
        # Делаем пользователя администратором с МИНИМАЛЬНЫМИ правами
        # ВАЖНО: нужно включить хотя бы одно право, иначе Telegram может отклонить
        try:
            # Пробуем сделать админом с минимальными правами
            success = await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=False,        # Не может менять инфу чата
                can_post_messages=False,      # Не может постить сообщения
                can_edit_messages=False,      # Не может редактировать сообщения
                can_delete_messages=False,    # Не может удалять сообщения
                can_invite_users=True,        # Может приглашать пользователей (минимальное право)
                can_restrict_members=False,   # Не может ограничивать участников
                can_pin_messages=False,       # Не может закреплять сообщения
                can_promote_members=False,    # Не может назначать админов
                can_manage_chat=False,        # Не может управлять чатом
                can_manage_video_chats=False, # Не может управлять видеочатами
                can_manage_topics=False       # Не может управлять темами
            )
            
            if success:
                print(f"SUCCESS: Пользователь {user_id} успешно назначен администратором")
                # Даем Telegram время обработать изменение прав
                await asyncio.sleep(2)
                return True
            else:
                print(f"ERROR: Не удалось назначить пользователя {user_id} администратором")
                # Пробуем альтернативный вариант с другим набором прав
                try:
                    success2 = await bot.promote_chat_member(
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
                    
                    if success2:
                        print(f"SUCCESS (вариант 2): Пользователь {user_id} назначен администратором")
                        await asyncio.sleep(2)
                        return True
                    else:
                        print(f"ERROR: Оба варианта не сработали для пользователя {user_id}")
                        return False
                        
                except Exception as e2:
                    print(f"ERROR при альтернативном назначении: {e2}")
                    return False
                    
        except Exception as e:
            print(f"ERROR: Исключение при назначении администратора: {e}")
            return False
            
    except Exception as e:
        print(f"ERROR: Общая ошибка при назначении администратора: {e}")
        return False

async def set_user_prefix(chat_id, user_id, points, is_owner=False):
    """Устанавливает префикс пользователю"""
    try:
        # Формируем префикс с баллами
        prefix = get_rank_for_title(points, is_owner=is_owner)
        
        print(f"DEBUG: Устанавливаю префикс '{prefix}' для пользователя {user_id}")
        
        # Сначала убеждаемся, что пользователь админ
        try:
            member_status = await bot.get_chat_member(chat_id, user_id)
            user_is_admin = member_status.status in ['administrator', 'creator']
            
            if not user_is_admin:
                print(f"DEBUG: Пользователь {user_id} не администратор, пытаюсь сделать админом...")
                admin_success = await make_user_admin_for_prefix(chat_id, user_id)
                if not admin_success:
                    print(f"ERROR: Не удалось сделать пользователя {user_id} администратором для префикса")
                    return False
                # Даем больше времени Telegram обработать
                await asyncio.sleep(3)
        except Exception as e:
            print(f"DEBUG: Ошибка при проверке статуса: {e}")
            return False
        
        # Пробуем установить префикс несколько раз с задержкой
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Ограничение Telegram: максимум 16 символов для префикса
                prefix_to_set = prefix[:16]
                
                print(f"DEBUG: Попытка {attempt + 1} установить префикс '{prefix_to_set}'")
                
                await bot.set_chat_administrator_custom_title(
                    chat_id=chat_id,
                    user_id=user_id,
                    custom_title=prefix_to_set
                )
                
                print(f"SUCCESS: Префикс '{prefix_to_set}' установлен для пользователя {user_id}")
                return True
                
            except Exception as e:
                print(f"ERROR (попытка {attempt + 1}): Не удалось установить префикс: {e}")
                if attempt < max_attempts - 1:
                    print(f"DEBUG: Жду 2 секунды перед следующей попыткой...")
                    await asyncio.sleep(2)
                else:
                    print(f"ERROR: Все попытки установить префикс провалились")
                    return False
        
    except Exception as e:
        print(f"ERROR: Критическая ошибка при установке префикса: {e}")
        return False

async def add_points_automatically(message, target_user_id, target_username):
    """Функция для автоматического добавления баллов"""
    chat_id = message.chat.id

    chat_points = load_chat_data(chat_id)
    chat_last_ranks = load_last_ranks(chat_id)

    # Сохраняем старые данные для сравнения
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
    print(f"DEBUG: Начисляю балл пользователю {target_user_id}. Было: {old_points}, стало: {new_points}")
    
    # Только для НЕ-владельцев пытаемся установить префикс
    if not is_owner:
        prefix_success = await set_user_prefix(chat_id, target_user_id, new_points, is_owner)
        
        if prefix_success:
            print(f"SUCCESS: Префикс обновлен для {target_user_id} -> {get_rank_for_title(new_points, is_owner)}")
        else:
            print(f"WARNING: Не удалось обновить префикс для {target_user_id}")
            # Не прерываем выполнение, продолжаем сохранять баллы
    else:
        print(f"DEBUG: Пользователь {target_user_id} владелец, префикс не обновляем")

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

async def is_creator(user_id):
    """Проверяет, является ли пользователь создателем"""
    return user_id == CREATOR_ID

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
        
    # Добавляем информацию о создателе
    creator_info = f"\n👑 Создатель бота: ID {CREATOR_ID}"
    
    help_text = f"""🎯 ДОСТУПНЫЕ КОМАНДЫ:

➕ Добавление баллов:
/add или /plus - добавить балл участнику (ответом на его сообщение)
/plus @username N - добавить N баллов пользователю (только создатель)*
/minus @username N - вычесть N баллов у пользователя (только создатель)*

📊 Информация:
/my - мой профиль (баллы и статус)
/top - ТОП-5 участников чата
/info - информация о системе репутации

⚙️ Админ-команды:
/update @username - обновить префикс пользователя (только создатель)*
/update 123456789 - обновить префикс по ID (только создатель)

🤖 Автоматически:
Баллы добавляются при словах: спасибо, благодарю, спс, саул, от души, мерси, спасибки и др.
⚠️ Благодарить можно не чаще 1 раза в 5 минут

⚠️ ВАЖНО О ПРЕФИКСАХ:
• Бот автоматически делает пользователей администраторами при начислении баллов
• Все административные права отключены (только префикс отображается)
• Префикс обновляется при каждом начислении баллов
• Формат префикса: ★☆☆ BASIC [8]
• Бот должен быть администратором с правом назначать администраторов

📝 *Примечание: Команды с @username работают только если пользователь уже получал баллы в этом чате.
   Для новых пользователей используйте /add (ответом на сообщение).{creator_info}"""

    msg = await message.reply(help_text)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["info"])
async def info(message: types.Message):
    """Информация о системе репутации"""
    if message.chat.type == 'private':
        return
        
    # ИСПРАВЛЕНИЕ: Исправляем отображение звезд
    info_text = f"""🌟 СИСТЕМА РЕПУТАЦИИ

📊 Уровни статусов:
★☆☆ BASIC [0-14] - Начинающий
★★☆ PRO [15-29] - Профессионал
★★★ ELITE [30+] - Элита
★☆☆ СМКЦ - Специальный статус владельца

🎯 Как получать баллы:
1. Ответьте /add на полезное сообщение
2. Поблагодарите участника словами: спасибо, благодарю, спс, саул, от души, мерси, спасибки
3. Получайте благодарности от других участников
4. Создатель может добавлять баллы командой /plus @username N

⏰ Важные правила:
• Благодарить можно не чаще 1 раза в 5 минут
• При повышении ранга все участники увидят праздничное уведомление! 🎉

📈 Автоматические действия:
• При начислении баллов бот сделает вас администратором (без прав)
• Ваш статус будет отображаться в префиксе над сообщениями: ★☆☆ BASIC [8]
• Префикс обновляется автоматически при каждом изменении баллов

👑 Создатель: ID {CREATOR_ID}"""

    msg = await message.reply(info_text)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["add", "pa", "добавить"])
async def add_points(message: types.Message):
    """Команда для ручного добавления балла (ответом на сообщение)"""
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
    """Команда для добавления N баллов пользователю по username (ТОЛЬКО ДЛЯ СОЗДАТЕЛЯ)"""
    if message.chat.type == 'private':
        return
    
    # ПРОВЕРКА: Только создатель может использовать эту команду
    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /plus")
        msg = await message.reply("❌ Эта команда доступна только создателю бота!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    command_args = message.get_args().strip()
    
    if not command_args:
        help_text = """➕ Добавление баллов пользователю (только создатель):

/plus @username N - добавить N баллов пользователю
/plus N @username - тоже работает

Примеры:
/plus @ulia 10 - добавить 10 баллов пользователю @ulia
/plus 5 @alex - добавить 5 баллов пользователю @alex

⚠️ Важно: Команда работает только если пользователь уже получал баллы в этом чате.
Для новых пользователей используйте /add (ответом на сообщение)."""
        
        msg = await message.reply(help_text)
        asyncio.create_task(delete_command_with_delay(message, msg, 15))
        return
    
    # Извлекаем username и количество баллов
    username, points = extract_username_and_points(command_args)
    
    if not username or points <= 0:
        msg = await message.reply("❌ Неверный формат. Используйте: /plus @username N\nПример: /plus @ulia 10")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    if points > 1000:
        msg = await message.reply("⚠️ Слишком много баллов за раз. Максимум 1000 за одну операцию.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    # Меняем баллы пользователя
    success, result_msg = await change_user_points(message, username, points, is_addition=True)
    
    msg = await message.reply(result_msg)
    asyncio.create_task(delete_command_with_delay(message, msg))

@dp.message_handler(commands=["minus"])
async def minus_points(message: types.Message):
    """Команда для вычитания N баллов у пользователя по username (ТОЛЬКО ДЛЯ СОЗДАТЕЛЯ)"""
    if message.chat.type == 'private':
        return
    
    # ПРОВЕРКА: Только создатель может использовать эту команду
    if not await is_creator(message.from_user.id):
        print(f"BLOCKED: Пользователь {message.from_user.id} пытался использовать /minus")
        msg = await message.reply("❌ Эта команда доступна только создателю бота!")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    command_args = message.get_args().strip()
    
    if not command_args:
        help_text = """➖ Вычитание баллов у пользователя (только создатель):

/minus @username N - вычесть N баллов у пользователя
/minus N @username - тоже работает

Примеры:
/minus @ulia 10 - вычесть 10 баллов у пользователя @ulia
/minus 5 @alex - вычесть 5 баллов у пользователя @alex

⚠️ Важно: Команда работает только если пользователь уже получал баллы в этом чате.
Для новых пользователей используйте /add (ответом на сообщение)."""
        
        msg = await message.reply(help_text)
        asyncio.create_task(delete_command_with_delay(message, msg, 15))
        return
    
    # Извлекаем username и количество баллов
    username, points = extract_username_and_points(command_args)
    
    if not username or points <= 0:
        msg = await message.reply("❌ Неверный формат. Используйте: /minus @username N\nПример: /minus @ulia 10")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    if points > 1000:
        msg = await message.reply("⚠️ Слишком много баллов за раз. Максимум 1000 за одну операцию.")
        asyncio.create_task(delete_command_with_delay(message, msg, 5))
        return
    
    # Меняем баллы пользователя (вычитание)
    success, result_msg = await change_user_points(message, username, points, is_addition=False)
    
    msg = await message.reply(result_msg)
    asyncio.create_task(delete_command_with_delay(message, msg))

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
    """Обновить префикс пользователя (админ) - теперь можно тегнуть пользователя (ТОЛЬКО ДЛЯ СОЗДАТЕЛЯ)"""
    if message.chat.type == 'private':
        return
    
    # ПРОВЕРКА: Только создатель может использовать эту команду
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
    
    # Пытаемся понять, что ввел пользователь: ID или username
    target_user_id = None
    username = None
    
    # Проверяем, это ID (только цифры) или username (начинается с @ или без)
    if command_args.isdigit():
        # Это ID
        target_user_id = int(command_args)
        # Ищем пользователя по ID в данных чата
        if target_user_id in chat_points:
            username = chat_points[target_user_id].get('username', f"user_{target_user_id}")
        else:
            msg = await message.reply(f"❌ Пользователь с ID {target_user_id} не найден в системе этого чата.")
            asyncio.create_task(delete_command_with_delay(message, msg))
            return
    else:
        # Это username (может быть с @ или без)
        username_input = command_args.lstrip('@')
        
        # Ищем пользователя по username в данных чата
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

    # Получаем данные пользователя
    user_data = chat_points[target_user_id]
    display_username = username or user_data.get('username', f"user_{target_user_id}")

    # Определяем, является ли пользователь владельцем
    is_owner = False
    try:
        member_status = await bot.get_chat_member(chat_id, target_user_id)
        is_owner = member_status.status in ['creator', 'владелец', 'Владелец']
    except:
        pass

    # ВАЖНОЕ ИСПРАВЛЕНИЕ: Формат префикса с баллами
    prefix = get_rank_for_title(user_data["points"], is_owner=is_owner)
    
    print(f"DEBUG: Обновляю префикс пользователя {target_user_id} (@{display_username}) на '{prefix}'")
    
    # Используем ту же функцию, что и для автоматического обновления
    prefix_success = await set_user_prefix(chat_id, target_user_id, user_data["points"], is_owner)
    
    if prefix_success:
        success_msg = f"✅ Префикс '{prefix}' успешно установлен!"
    else:
        success_msg = f"❌ Не удалось установить префикс. Убедитесь, что бот администратор и имеет права на назначение администраторов."

    owner_text = " (владелец)" if is_owner else ""
    response = f"{success_msg}\n\n"
    # ИСПРАВЛЕНИЕ: Используем ссылку на профиль
    response += f"👤 Пользователь: <a href='tg://user?id={target_user_id}'>{display_username}</a>{owner_text}\n"
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
    print(f"\n👑 СОЗДАТЕЛЬ БОТА: ID {CREATOR_ID}")
    print("\n🌟 СИСТЕМА СТАТУСОВ:")
    print("   ★☆☆ BASIC [0-14]")
    print("   ★★☆ PRO [15-29]")
    print("   ★★★ ELITE [30+]")
    print("   ★☆☆ СМКЦ (только для владельца)")
    print("\n🎯 ДОСТУПНЫЕ КОМАНДЫ ДЛЯ ВСЕХ:")
    print("   /help - все команды")
    print("   /my - мой профиль")
    print("   /top - топ-5 участников")
    print("   /add - добавить балл (ответом на сообщение)")
    print("   /info - о системе")
    print("\n🔐 ЗАЩИЩЕННЫЕ КОМАНДЫ (ТОЛЬКО СОЗДАТЕЛЬ):")
    print(f"   /plus @username N - добавить N баллов (создатель: {CREATOR_ID})")
    print(f"   /minus @username N - вычесть N баллов (создатель: {CREATOR_ID})")
    print(f"   /update @username - обновить префикс (создатель: {CREATOR_ID})")
    print("\n⚠️ ВАЖНО О КОМАНДАХ С @USERNAME:")
    print("   • Работают только если пользователь уже получал баллы в чате")
    print("   • Для новых пользователей используйте /add (ответом на сообщение)")
    print("   • Или сначала дайте пользователю балл через благодарность")
    print("\n⚠️ АВТОМАТИЧЕСКИЕ ДЕЙСТВИЯ:")
    print("   1. Бот автоматически делает пользователей администраторами")
    print("   2. Все административные права отключены (кроме приглашения)")
    print("   3. Префикс отображается в виде: ★☆☆ BASIC [8]")
    print("   4. Префикс обновляется при КАЖДОМ начислении баллов")
    print("\n⏰ ОГРАНИЧЕНИЯ:")
    print("   • Благодарить можно 1 раз в 5 минут")
    print("   • Команды удаляются через 30 секунд")
    print("   • Каждая группа имеет отдельную базу данных")
    print("   • Бот игнорирует личные сообщения")
    print("   • Максимум 1000 баллов за одну операцию")
    print("\n💬 Автоматическое повышение при словах:")
    print(f"   {', '.join(THANK_WORDS[:6])}...")
    print("=" * 60)
    executor.start_polling(dp, skip_updates=True)
