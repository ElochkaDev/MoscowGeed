import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv
from uuid import uuid4
from collections import defaultdict
from datetime import datetime
import pytz
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

API_TOKEN = os.getenv('BOT_TOKEN')
GROUP_ID = os.getenv('GROUP_ID')

requests_db = {}
leaders_stats = defaultdict(int)
user_names = {}


if not API_TOKEN or not GROUP_ID:
    raise ValueError("Абоба ты переменные окружения не добавил гениус!")

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class RequestStates(StatesGroup):
    waiting_for_request = State()

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply(f"🚀 Здравствуйте, {message.from_user.full_name}!\n\nВы в Москве, а значит — среди друзей!\nЭтот бот создан, чтобы участники ЛР могли:  \n• Быстро получить помощь в столице\n• Найти сопровождающего из сообщества\n• Обменяться полезными контактами\n\n▶️ Напишите, чем вам помочь, или посмотрите /help.")

@dp.message_handler(commands=['request'])
async def start_request(message: types.Message):
    example_request = """📋 Пример запроса:
    
Дата: 25 мая 2024
Время: 14:00-17:00
Цель: Встреча с партнерами
Нужна помощь: Логистика до места встречи
Формат сопровождения: Гид на 2 часа

✏️ Пришлите ваш запрос в аналогичном формате"""
    
    await message.reply(example_request)
    await RequestStates.waiting_for_request.set()

@dp.message_handler(state=RequestStates.waiting_for_request)
async def handle_request(message: types.Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        request_text = message.text
        request_id = str(uuid4())
        
        requests_db[request_id] = {
            'user_id': user_id,
            'request_text': request_text,
            'username': message.from_user.username,
            'active': True
        }

        keyboard = InlineKeyboardMarkup()
        accept_button = InlineKeyboardButton(
            text="✅ Принять запрос",
            callback_data=f"accept|{request_id}"
        )
        keyboard.add(accept_button)

        try:
            group_message = await bot.send_message(
                chat_id=GROUP_ID,
                text=f"🚨 Новый запрос от @{message.from_user.username}:\n\n{request_text}",
                reply_markup=keyboard
            )
            requests_db[request_id]['group_message_id'] = group_message.message_id
            logger.info(f"Запрос {request_id} отправлен в группу")
            
        except Exception as group_error:
            logger.error(f"Ошибка отправки в группу: {group_error}")
            await message.reply("❌ Ошибка отправки запроса. Попробуйте позже.")
            return
        
        await message.reply("✅ Ваш запрос принят и отправлен в сообщество! Ожидайте откликов.")
        await state.finish()
        
    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {e}")
        await message.reply("❌ Произошла ошибка при обработке запроса")

@dp.callback_query_handler(lambda c: c.data.startswith('accept|'))
async def handle_accept(callback_query: types.CallbackQuery):
    try:
        request_id = callback_query.data.split('|', 1)[1]
        request_data = requests_db.get(request_id)
        
        if not request_data or not request_data.get('active'):
            await callback_query.answer("Запрос недоступен")
            return


        helper_id = callback_query.from_user.id
        leaders_stats[helper_id] += 1
        user_names[helper_id] = callback_query.from_user.username
        requests_db[request_id]['active'] = False

        await bot.send_message(
            chat_id=request_data['user_id'],
            text=f"🎉 Ваш запрос принял @{callback_query.from_user.username}!\n\n" 
                 f"Свяжитесь с ним для уточнения деталей: @{callback_query.from_user.username}"
        )
        
        try:
            await bot.edit_message_reply_markup(
                chat_id=GROUP_ID,
                message_id=request_data['group_message_id'],
                reply_markup=None
            )
        except Exception as edit_error:
            logger.error(f"Ошибка редактирования сообщения: {edit_error}")

        del requests_db[request_id]
        
        await callback_query.answer("Вы успешно приняли запрос!")
        logger.info(f"Запрос {request_id} принят пользователем @{callback_query.from_user.username}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки принятия: {e}")
        await callback_query.answer("Произошла ошибка")

@dp.message_handler(commands=['leaders'])
async def show_leaders(message: types.Message):
    try:
        sorted_leaders = sorted(
            leaders_stats.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        if not sorted_leaders:
            await message.reply("🏆 Рейтинг пока пуст. Будьте первым!")
            return

        leaderboard = "🏆 Топ помощников сообщества:\n\n"
        for idx, (user_id, count) in enumerate(sorted_leaders, 1):
            username = user_names.get(user_id, 'Аноним')
            leaderboard += (
                f"{idx}. @{username}\n"
                f"   Принято запросов: {count}\n"
                f"   {'⭐' * min(count, 5)}\n\n"
            )

        await message.reply(leaderboard)
        
    except Exception as e:
        logger.error(f"Ошибка формирования рейтинга: {e}")
        await message.reply("❌ Не удалось получить рейтинг")


@dp.message_handler(commands=['help'])
async def send_help(message: types.Message):
    await message.reply(f"""📌 Помощь по боту «Дежурный по Москве»

    Я помогаю участникам сообщества «Лидеры России» быстро находить поддержку в столице. Вот что я умею:

    🔹 Основные команды:
    /start — Начать работу с ботом
    /help — Показать это сообщение
    /time — Показать время в Москве
    /request — Оставить запрос на помощь (гид, встреча, советы)
    /leaders — Рейтинг волонтеров
    /contacts — Полезные контакты сообщества в Москве

    🔹 Как это работает?

    Вы отправляете запрос через /request (например: «Нужен сопровождающий 25 мая на встречу в МГУ»).

    Я автоматически опрашиваю московских участников ЛР.

    Как только найдется доброволец — вы получите его контакты для связи.

    🤝 Важно:
    • Все участники проверены сообществом.
    • Бот лишь соединяет вас — детали обсуждаются лично.

    Пример запроса:
    «Ищу гида по деловому центру “Москва-Сити” 30 мая с 14:00 до 17:00»""")

@dp.message_handler(commands=['contacts'])
async def send_contacts(message: types.Message):
    await message.reply(f"""Автономная некоммерческая организация «Россия – страна возможностей»

    Место нахождения юридического лица: город Москва

    Адрес юридического лица: 109004, Город Москва, вн. тер. г. муниципальный округ Таганский, ул. Станиславского, д. 21, стр. 3, помещ. I, ком. 70

    Почтовый адрес: 123112, г. Москва, а/я 100

    ОГРН 1187700010464
    ИНН 9710063040 / КПП 770901001
    ОКПО 29751572

    Банковские реквизиты:
    Банк: ПАО СБЕРБАНК Г. МОСКВА
    Р/с 40703810738000009735
    К/с 30101810400000000225
    БИК 044525225

    E-mail: info@rsv.ru
    тел.: 8 (495) 198-88-92""")

@dp.message_handler(commands=['time'])
async def show_moscow_time(message: types.Message):
    try:
        moscow_tz = pytz.timezone('Europe/Moscow')
        current_time = datetime.now(moscow_tz)

        formatted_time = current_time.strftime(
            "Текущее время в Москве:\n"
            "%H:%M:%S\n"
            "Дата: %d.%m.%Y"
        )

        await message.reply(f"🕒 {formatted_time} 📅")
        
    except Exception as e:
        logger.error(f"Ошибка получения времени: {str(e).encode('utf-8')}")
        await message.reply("❌ Не удалось получить время")

if __name__ == '__main__':
    logger.info("Бот запущен")
    executor.start_polling(dp, skip_updates=True)