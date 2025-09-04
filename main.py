import os
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command
from aiogram.utils import executor

# ==================== КОНФИГУРАЦИЯ ====================
load_dotenv()


class Config:
    def __init__(self):
        load_dotenv()
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')

        # Безопасное получение ADMIN_IDS
        admin_ids_str = os.getenv('ADMIN_IDS', '')
        self.ADMIN_IDS = []
        if admin_ids_str:
            try:
                self.ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip()]
            except ValueError:
                logger.warning("Неверный формат ADMIN_IDS в .env файле")

        self.LOG_CHAT_ID = os.getenv('LOG_CHAT_ID')
        self.DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

        if not self.BOT_TOKEN:
            raise ValueError("❌ BOT_TOKEN не найден в .env файле!")

config = Config()

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=config.BOT_TOKEN, parse_mode='HTML')
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


# ==================== СОСТОЯНИЯ ====================
class Form(StatesGroup):
    choosing_category = State()
    writing_message = State()
    broadcast_message = State()
    user_lookup = State()


# ==================== УТИЛИТЫ ====================
def ensure_dirs():
    """Создает необходимые папки"""
    for directory in ['logs', 'data']:
        if not os.path.exists(directory):
            os.makedirs(directory)


def get_timestamp():
    """Возвращает форматированное время"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save_message(category: str, user_data: dict, message_text: str):
    """Сохраняет сообщение в файл"""
    try:
        filename = f"logs/{category}.txt"
        timestamp = get_timestamp()

        entry = (
            f"{timestamp} - {user_data['username']} "
            f"(ID: {user_data['user_id']}): {message_text}\n"
        )

        with open(filename, 'a', encoding='utf-8') as f:
            f.write(entry)

        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        return False


def get_stats():
    """Возвращает статистику сообщений"""
    stats = {}
    categories = ["Работа", "Учёба", "Прочее"]

    for category in categories:
        filename = f"logs/{category}.txt"
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                stats[category] = len(f.readlines())
        else:
            stats[category] = 0

    return stats


def get_user_stats():
    """Собирает статистику по пользователям (заглушка)"""
    return {
        'total_users': 150,
        'active_today': 42,
        'online_now': 8,
        'messages_today': 125
    }


async def log_action(user_id: int, action: str):
    """Логирует действия в чат"""
    if config.LOG_CHAT_ID:
        try:
            await bot.send_message(
                config.LOG_CHAT_ID,
                f"📝 Действие: {action}\n👤 User ID: {user_id}\n⏰ Время: {get_timestamp()}"
            )
        except Exception as e:
            logger.error(f"Ошибка логирования: {e}")


# ==================== КЛАВИАТУРЫ ====================
def create_main_keyboard():
    """Клавиатура для выбора категории"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("Работа", "Учёба")
    keyboard.row("Прочее")
    return keyboard


def create_admin_keyboard():
    """Клавиатура админ-панели"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📊 Статистика", "📢 Рассылка")
    keyboard.row("👥 Пользователи", "🔍 Найти пользователя")
    keyboard.row("🔙 Главное меню")
    return keyboard


# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message_handler(Command('start', 'help'))
async def cmd_start(message: types.Message):
    """Обработчик команд /start и /help"""
    user_id = message.from_user.id

    welcome_text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Я помогу вам сохранить ваше сообщение по категориям.\n\n"
        "<b>📋 Доступные команды:</b>\n"
        "/start - начать работу\n"
        "/help - помощь\n"
        "/cancel - отменить действие\n"
    )

    if config.is_admin(user_id):
        welcome_text += (
            "/admin - админ-панель\n"
            "/stats - статистика\n"
            "/users - пользователи\n"
            "/broadcast - рассылка\n"
            "/userinfo - информация о пользователе\n"
        )

    await message.answer(welcome_text, reply_markup=create_main_keyboard())
    await Form.choosing_category.set()
    await log_action(user_id, "started bot")


@dp.message_handler(Command('cancel'), state='*')
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    if current_state:
        await state.finish()
        await message.answer(
            "❌ Действие отменено.\n\n"
            "Вы можете начать заново с /start",
            reply_markup=create_main_keyboard()
        )
        await log_action(message.from_user.id, "cancelled action")
    else:
        await message.answer("Нечего отменять 🤷‍♂️")


# ==================== АДМИН-КОМАНДЫ ====================
@dp.message_handler(Command('admin'))
async def cmd_admin(message: types.Message):
    """Админ-панель"""
    user_id = message.from_user.id

    if not config.is_admin(user_id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    await message.answer(
        "👑 <b>Админ-панель</b>\n\n"
        "Выберите действие:",
        reply_markup=create_admin_keyboard()
    )
    await log_action(user_id, "opened admin panel")


@dp.message_handler(Command('stats'))
async def cmd_stats(message: types.Message):
    """Статистика бота"""
    user_id = message.from_user.id

    if not config.is_admin(user_id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    stats = get_stats()
    user_stats = get_user_stats()
    total_messages = sum(stats.values())

    stats_text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {user_stats['total_users']}\n"
        f"💬 Сообщений сегодня: {user_stats['messages_today']}\n"
        f"📈 Активных сегодня: {user_stats['active_today']}\n"
        f"🔄 Онлайн сейчас: {user_stats['online_now']}\n\n"
        "📁 <b>Сообщений по категориям:</b>\n"
        f"💼 Работа: {stats.get('Работа', 0)}\n"
        f"🎓 Учёба: {stats.get('Учёба', 0)}\n"
        f"📦 Прочее: {stats.get('Прочее', 0)}\n\n"
        f"📈 Всего сообщений: {total_messages}"
    )

    await message.answer(stats_text)
    await log_action(user_id, "viewed statistics via command")


@dp.message_handler(Command('users'))
async def cmd_users(message: types.Message):
    """Список пользователей"""
    user_id = message.from_user.id

    if not config.is_admin(user_id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    user_stats = get_user_stats()

    users_text = (
        "👥 <b>Статистика пользователей:</b>\n\n"
        f"👤 Всего пользователей: {user_stats['total_users']}\n"
        f"🚀 Активных за 24ч: {user_stats['active_today']}\n"
        f"💬 Сообщений сегодня: {user_stats['messages_today']}\n"
        f"🟢 Онлайн сейчас: {user_stats['online_now']}\n\n"
        "<i>Для подробной информации используйте /userinfo [ID]</i>"
    )

    await message.answer(users_text)
    await log_action(user_id, "viewed users list")


@dp.message_handler(Command('broadcast'))
async def cmd_broadcast(message: types.Message):
    """Рассылка сообщения"""
    user_id = message.from_user.id

    if not config.is_admin(user_id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    # Проверяем есть ли текст для рассылки
    if len(message.text.split()) < 2:
        await message.answer(
            "📢 <b>Рассылка сообщений</b>\n\n"
            "Использование: /broadcast Ваш текст сообщения\n\n"
            "Или используйте кнопку '📢 Рассылка' для интерактивного режима"
        )
        return

    broadcast_text = ' '.join(message.text.split()[1:])
    user_stats = get_user_stats()

    await message.answer(
        f"✅ <b>Рассылка запущена!</b>\n\n"
        f"📝 Сообщение: {broadcast_text}\n"
        f"👥 Получателей: {user_stats['total_users']}\n\n"
        f"<i>Это демо-режим. В реальном боте сообщение будет отправлено всем пользователям.</i>"
    )
    await log_action(user_id, f"broadcast via command: {broadcast_text[:50]}...")


@dp.message_handler(Command('userinfo'))
async def cmd_userinfo(message: types.Message, state: FSMContext):
    """Информация о пользователе"""
    user_id = message.from_user.id

    if not config.is_admin(user_id):
        await message.answer("❌ У вас нет прав администратора!")
        return

    # Если передан ID пользователя
    if len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])

            user_info = (
                f"👤 <b>Информация о пользователе:</b>\n\n"
                f"🆔 ID: {target_id}\n"
                f"👤 Имя: Пользователь #{target_id}\n"
                f"📅 Зарегистрирован: 2024-01-15\n"
                f"💬 Сообщений: 42\n"
                f"🚀 Статус: Активный\n"
                f"👑 Роль: Пользователь"
            )

            await message.answer(user_info)
            await log_action(user_id, f"searched user info for ID: {target_id}")

        except ValueError:
            await message.answer("❌ Неверный формат ID пользователя!")
    else:
        # Запрос ID пользователя
        await message.answer(
            "🔍 <b>Поиск пользователя</b>\n\n"
            "Введите ID пользователя для получения информации:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await Form.user_lookup.set()
        await log_action(user_id, "started user lookup")


# ==================== ОБРАБОТЧИКИ СОСТОЯНИЙ ====================
@dp.message_handler(state=Form.choosing_category)
async def process_category(message: types.Message, state: FSMContext):
    """Обработка выбора категории"""
    if message.text not in ["Работа", "Учёба", "Прочее"]:
        await message.answer("Пожалуйста, выберите категорию из кнопок ниже:")
        return

    await state.update_data(chosen_category=message.text)
    await Form.writing_message.set()

    await message.answer(
        f"📝 Вы выбрали: <b>{message.text}</b>\n\n"
        "Теперь напишите ваше сообщение:\n\n"
        "<i>Используйте /cancel для отмены</i>",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await log_action(message.from_user.id, f"selected category: {message.text}")


@dp.message_handler(state=Form.writing_message)
async def process_message(message: types.Message, state: FSMContext):
    """Обработка сообщения пользователя"""
    user_data = await state.get_data()
    category = user_data.get('chosen_category')

    if not category:
        await message.answer("❌ Ошибка. Начните с /start")
        await state.finish()
        return

    user_info = {
        'user_id': message.from_user.id,
        'username': message.from_user.username or message.from_user.first_name or "Аноним",
        'full_name': message.from_user.full_name
    }

    # Сохраняем сообщение
    success = save_message(category, user_info, message.text)

    if success:
        response_text = (
            f"✅ <b>Сообщение сохранено!</b>\n\n"
            f"<b>Категория:</b> {category}\n"
            f"<b>Ваше сообщение:</b>\n{message.text}\n\n"
            "Спасибо за ваше обращение! 🙏\n\n"
            "Нажмите /start для нового сообщения"
        )
        logger.info(f"Сообщение сохранено: {user_info['username']} - {category}")
    else:
        response_text = "❌ Произошла ошибка при сохранении. Попробуйте позже."

    await message.answer(response_text, reply_markup=create_main_keyboard())
    await state.finish()
    await log_action(message.from_user.id, f"saved message in {category}")


@dp.message_handler(state=Form.broadcast_message)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    """Отправка рассылки"""
    user_stats = get_user_stats()

    await message.answer(
        f"✅ <b>Рассылка запущена!</b>\n\n"
        f"📝 Сообщение: {message.text}\n"
        f"👥 Получателей: {user_stats['total_users']}\n\n"
        f"<i>Это демо-режим. В реальном боте сообщение будет отправлено всем пользователям.</i>",
        reply_markup=create_admin_keyboard()
    )
    await state.finish()
    await log_action(message.from_user.id, f"sent broadcast: {message.text[:50]}...")


@dp.message_handler(state=Form.user_lookup)
async def process_user_lookup(message: types.Message, state: FSMContext):
    """Обработка поиска пользователя"""
    try:
        target_id = int(message.text)

        user_info = (
            f"👤 <b>Информация о пользователе:</b>\n\n"
            f"🆔 ID: {target_id}\n"
            f"👤 Имя: Пользователь #{target_id}\n"
            f"📅 Зарегистрирован: 2024-01-15\n"
            f"💬 Сообщений: 42\n"
            f"🚀 Статус: Активный\n"
            f"👑 Роль: Пользователь\n\n"
            f"<i>Это демо-информация. В реальном боте здесь будут реальные данные.</i>"
        )

        await message.answer(user_info, reply_markup=create_admin_keyboard())
        await log_action(message.from_user.id, f"found user info for ID: {target_id}")

    except ValueError:
        await message.answer("❌ Неверный формат ID! Введите число:")
        return

    await state.finish()


# ==================== АДМИН-КНОПКИ ====================
@dp.message_handler(lambda message: message.text == "📊 Статистика" and config.is_admin(message.from_user.id))
async def admin_stats(message: types.Message):
    """Статистика бота через кнопку"""
    stats = get_stats()
    user_stats = get_user_stats()
    total_messages = sum(stats.values())

    stats_text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: {user_stats['total_users']}\n"
        f"💬 Сообщений сегодня: {user_stats['messages_today']}\n"
        f"📈 Активных сегодня: {user_stats['active_today']}\n"
        f"🔄 Онлайн сейчас: {user_stats['online_now']}\n\n"
        "📁 <b>Сообщений по категориям:</b>\n"
        f"💼 Работа: {stats.get('Работа', 0)}\n"
        f"🎓 Учёба: {stats.get('Учёба', 0)}\n"
        f"📦 Прочее: {stats.get('Прочее', 0)}\n\n"
        f"📈 Всего сообщений: {total_messages}"
    )

    await message.answer(stats_text)
    await log_action(message.from_user.id, "viewed statistics via button")


@dp.message_handler(lambda message: message.text == "📢 Рассылка" and config.is_admin(message.from_user.id))
async def admin_broadcast_start(message: types.Message):
    """Начало рассылки через кнопку"""
    await message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Отправьте сообщение для рассылки всем пользователям:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await Form.broadcast_message.set()
    await log_action(message.from_user.id, "started broadcast via button")


@dp.message_handler(lambda message: message.text == "👥 Пользователи" and config.is_admin(message.from_user.id))
async def admin_users(message: types.Message):
    """Информация о пользователях через кнопку"""
    user_stats = get_user_stats()

    users_text = (
        "👥 <b>Статистика пользователей:</b>\n\n"
        f"👤 Всего пользователей: {user_stats['total_users']}\n"
        f"🚀 Активных за 24ч: {user_stats['active_today']}\n"
        f"💬 Сообщений сегодня: {user_stats['messages_today']}\n"
        f"🟢 Онлайн сейчас: {user_stats['online_now']}\n\n"
        "Для поиска конкретного пользователя используйте кнопку '🔍 Найти пользователя'"
    )

    await message.answer(users_text)
    await log_action(message.from_user.id, "viewed users via button")


@dp.message_handler(lambda message: message.text == "🔍 Найти пользователя" and config.is_admin(message.from_user.id))
async def admin_find_user(message: types.Message):
    """Поиск пользователя через кнопку"""
    await message.answer(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите ID пользователя для получения информации:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await Form.user_lookup.set()
    await log_action(message.from_user.id, "started user search via button")


@dp.message_handler(lambda message: message.text == "🔙 Главное меню")
async def back_to_main(message: types.Message):
    """Возврат в главное меню"""
    await message.answer(
        "📋 <b>Главное меню</b>\n\n"
        "Выберите категорию:",
        reply_markup=create_main_keyboard()
    )
    await Form.choosing_category.set()
    await log_action(message.from_user.id, "returned to main menu")


# ==================== ЗАПУСК БОТА ====================
async def on_startup(dp):
    """Действия при запуске бота"""
    ensure_dirs()
    logger.info("=" * 50)
    logger.info("🤖 Бот успешно запущен!")
    logger.info(f"👑 Администраторы: {config.ADMIN_IDS}")
    logger.info(f"🐛 Debug mode: {config.DEBUG}")
    logger.info("=" * 50)

    if config.LOG_CHAT_ID:
        try:
            await bot.send_message(config.LOG_CHAT_ID, "✅ Бот запущен и готов к работе!")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление: {e}")


async def on_shutdown(dp):
    """Действия при остановке бота"""
    logger.info("⛔ Бот остановлен!")
    await bot.close()


if __name__ == '__main__':
    ensure_dirs()
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )