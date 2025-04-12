import logging
from typing import Optional, Dict, List
from datetime import datetime
from config import BOT_TOKEN, GROUP_ID
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = BOT_TOKEN
if not BOT_TOKEN:
    raise ValueError("Пожалуйста, установите переменную среды BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

@dataclass
class User:
    id: int
    full_name: str
    phone: str
    telegram_username: str
    role: str
    season: Optional[int] = None
    status: Optional[str] = None
    rating: Optional[float] = None
    guests_helped: int = 0

@dataclass
class Request:
    id: int
    leader_id: int
    duty_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    request_text: Optional[str] = None
    status: str = "pending"
    feedback: Optional[str] = None
    rating: Optional[int] = None

db_users: Dict[int, User] = {}
db_requests: Dict[int, Request] = {}
request_counter = 0

class Form(StatesGroup):
    full_name = State()
    phone = State()
    telegram_username = State()
    role = State()
    season = State()
    status = State()
    request_text = State()
    dates = State()
    feedback = State()
    rating = State()

async def get_main_keyboard(user: User) -> ReplyKeyboardMarkup:
    if user.role == "leader":
        buttons = [
            [KeyboardButton(text="Создать запрос")],
            [KeyboardButton(text="Мои запросы")],
            [KeyboardButton(text="Оставить отзыв")],
        ]
    else:
        buttons = [
            [KeyboardButton(text="Доступные запросы")],
            [KeyboardButton(text="Мои принятые запросы")],
            [KeyboardButton(text="Мой профиль")],
        ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def send_request_to_duty_chat(request: Request, leader: User):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(
            text="Принять запрос",
            callback_data=f"accept_{request.id}",
        ),
        InlineKeyboardButton(
            text="Отклонить запрос",
            callback_data=f"reject_{request.id}",
        ),
        InlineKeyboardButton(
            text="Частично принять",
            callback_data=f"partial_{request.id}",
        ),
    )
    
    text = (
        f"📌 Новый запрос от Лидера России\n\n"
        f"👤 {leader.full_name}\n"
        f"📞 {leader.phone}\n"
        f"🔹 Статус: {leader.status}\n"
        f"🔹 Сезон: {leader.season}\n"
        f"📅 Даты: {request.start_date} - {request.end_date}\n"
        f"📝 Запрос: {request.request_text}"
    )
    
    logger.info(f"Request sent to duty chat:\n{text}")
    
    await bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        reply_markup=builder.as_markup(),
    )

@dp.message(Command("start"))
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    
    if message.from_user.id in db_users:
        user = db_users[message.from_user.id]
        keyboard = await get_main_keyboard(user)
        await message.answer(
            f"С возвращением, {user.full_name}!",
            reply_markup=keyboard,
        )
    else:
        await state.set_state(Form.role)
        await message.answer(
            "Добро пожаловать в бота 'Дежурный по Москве'!\n\n"
            "Вы участник сообщества 'Лидеры России'?",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Я Лидер России")],
                    [KeyboardButton(text="Я Дежурный по Москве")],
                ],
                resize_keyboard=True,
            ),
        )

@dp.message(Form.role)
async def process_role(message: Message, state: FSMContext) -> None:
    if message.text == "Я Лидер России":
        await state.update_data(role="leader")
        await state.set_state(Form.full_name)
        await message.answer(
            "Введите ваше ФИО:",
            reply_markup=ReplyKeyboardRemove(),
        )
    elif message.text == "Я Дежурный по Москве":
        await state.update_data(role="duty")
        await state.set_state(Form.full_name)
        await message.answer(
            "Введите ваше ФИО:",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer("Пожалуйста, выберите вариант из предложенных.")

@dp.message(Form.full_name)
async def process_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=message.text)
    await state.set_state(Form.phone)
    await message.answer("Введите ваш номер телефона:")

@dp.message(Form.phone)
async def process_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text)
    await state.set_state(Form.telegram_username)
    await message.answer("Введите ваш username в Telegram (без @):")

@dp.message(Form.telegram_username)
async def process_telegram_username(message: Message, state: FSMContext) -> None:
    data = await state.update_data(telegram_username=message.text)
    
    if data["role"] == "leader":
        await state.set_state(Form.season)
        await message.answer("Введите номер сезона, в котором вы участвовали (1-5):")
    else:
        user = User(
            id=message.from_user.id,
            full_name=data["full_name"],
            phone=data["phone"],
            telegram_username=data["telegram_username"],
            role=data["role"],
        )
        db_users[message.from_user.id] = user
        
        keyboard = await get_main_keyboard(user)
        await message.answer(
            "Регистрация завершена! Теперь вы можете принимать запросы от Лидеров России.",
            reply_markup=keyboard,
        )
        await state.clear()

@dp.message(Form.season)
async def process_season(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit() or int(message.text) not in range(1, 6):
        await message.answer("Пожалуйста, введите число от 1 до 5:")
        return
    
    await state.update_data(season=int(message.text))
    await state.set_state(Form.status)
    await message.answer(
        "Выберите ваш статус участия:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Полуфиналист")],
                [KeyboardButton(text="Финалист")],
                [KeyboardButton(text="Победитель")],
            ],
            resize_keyboard=True,
        ),
    )

@dp.message(Form.status)
async def process_status(message: Message, state: FSMContext) -> None:
    if message.text not in ["Полуфиналист", "Финалист", "Победитель"]:
        await message.answer("Пожалуйста, выберите вариант из предложенных.")
        return
    
    data = await state.update_data(status=message.text.lower())
    user = User(
        id=message.from_user.id,
        full_name=data["full_name"],
        phone=data["phone"],
        telegram_username=data["telegram_username"],
        role=data["role"],
        season=data["season"],
        status=data["status"],
    )
    db_users[message.from_user.id] = user
    
    keyboard = await get_main_keyboard(user)
    await message.answer(
        "Регистрация завершена! Теперь вы можете создавать запросы на поддержку.",
        reply_markup=keyboard,
    )
    await state.clear()

@dp.message(F.text == "Создать запрос")
async def create_request(message: Message, state: FSMContext) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "leader":
        await message.answer("Эта функция доступна только для Лидеров России.")
        return
    
    await state.set_state(Form.request_text)
    await message.answer(
        "Опишите ваш запрос (в чем вам нужна помощь в Москве):",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(Form.request_text)
async def process_request_text(message: Message, state: FSMContext) -> None:
    await state.update_data(request_text=message.text)
    await state.set_state(Form.dates)
    await message.answer(
        "Укажите даты вашего пребывания в Москве (например: 01.09.2023-05.09.2023):"
    )

@dp.message(Form.dates)
async def process_dates(message: Message, state: FSMContext) -> None:
    try:
        start_date, end_date = message.text.split("-")
        start_date = start_date.strip()
        end_date = end_date.strip()
        datetime.strptime(start_date, "%d.%m.%Y")
        datetime.strptime(end_date, "%d.%m.%Y")
    except ValueError:
        await message.answer("Пожалуйста, введите даты в формате ДД.ММ.ГГГГ-ДД.ММ.ГГГГ")
        return
    
    data = await state.update_data(start_date=start_date, end_date=end_date)
    
    global request_counter
    request_counter += 1
    
    request = Request(
        id=request_counter,
        leader_id=message.from_user.id,
        start_date=data["start_date"],
        end_date=data["end_date"],
        request_text=data["request_text"],
    )
    db_requests[request_counter] = request
    
    leader = db_users[message.from_user.id]
    await send_request_to_duty_chat(request, leader)
    
    keyboard = await get_main_keyboard(leader)
    await message.answer(
        "Ваш запрос отправлен Дежурным по Москве! Ожидайте предложений помощи.",
        reply_markup=keyboard,
    )
    await state.clear()

@dp.message(F.text == "Доступные запросы")
async def show_available_requests(message: Message) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "duty":
        await message.answer("Эта функция доступна только для Дежурных по Москве.")
        return
    
    pending_requests = [r for r in db_requests.values() if r.status == "pending"]
    
    if not pending_requests:
        await message.answer("На данный момент нет доступных запросов.")
        return
    
    for request in pending_requests[:5]:
        leader = db_users[request.leader_id]
        builder = InlineKeyboardBuilder()
        builder.add(
            InlineKeyboardButton(
                text="Принять запрос",
                callback_data=f"accept_{request.id}",
            ),
            InlineKeyboardButton(
                text="Отклонить запрос",
                callback_data=f"reject_{request.id}",
            ),
            InlineKeyboardButton(
                text="Частично принять",
                callback_data=f"partial_{request.id}",
            ),
        )
        
        text = (
            f"📌 Запрос #{request.id}\n\n"
            f"👤 {leader.full_name}\n"
            f"📞 {leader.phone}\n"
            f"🔹 Статус: {leader.status}\n"
            f"🔹 Сезон: {leader.season}\n"
            f"📅 Даты: {request.start_date} - {request.end_date}\n"
            f"📝 Запрос: {request.request_text}"
        )
        
        await message.answer(
            text,
            reply_markup=builder.as_markup(),
        )

@dp.callback_query(F.data.startswith("accept_"))
async def accept_request(callback: types.CallbackQuery) -> None:
    request_id = int(callback.data.split("_")[1])
    request = db_requests.get(request_id)
    
    if not request:
        await callback.answer("Запрос не найден.")
        return
    
    if request.status != "pending":
        await callback.answer("Этот запрос уже обработан.")
        return
    
    duty = db_users[callback.from_user.id]
    request.duty_id = duty.id
    request.status = "accepted"
    
    leader = db_users[request.leader_id]
    
    await bot.send_message(
        chat_id=request.leader_id,
        text=(
            f"🎉 Ваш запрос принят!\n\n"
            f"Дежурный по Москве:\n"
            f"👤 {duty.full_name}\n"
            f"📞 {duty.phone}\n"
            f"📱 @{duty.telegram_username}\n\n"
            f"Свяжитесь с ним для уточнения деталей."
        ),
    )
    
    duty.guests_helped += 1
    
    await callback.answer("Вы приняли этот запрос.")
    await callback.message.edit_text(
        f"✅ Вы приняли запрос #{request_id}",
        reply_markup=None,
    )

@dp.callback_query(F.data.startswith("reject_"))
async def reject_request(callback: types.CallbackQuery) -> None:
    request_id = int(callback.data.split("_")[1])
    request = db_requests.get(request_id)
    
    if not request:
        await callback.answer("Запрос не найден.")
        return
    
    if request.status != "pending":
        await callback.answer("Этот запрос уже обработан.")
        return
    
    request.status = "rejected"
    
    await callback.answer("Вы отклонили этот запрос.")
    await callback.message.edit_text(
        f"❌ Вы отклонили запрос #{request_id}",
        reply_markup=None,
    )

@dp.callback_query(F.data.startswith("partial_"))
async def partial_accept(callback: types.CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.split("_")[1])
    request = db_requests.get(request_id)
    
    if not request:
        await callback.answer("Запрос не найден.")
        return
    
    if request.status != "pending":
        await callback.answer("Этот запрос уже обработан.")
        return
    
    await state.update_data(request_id=request_id)
    await state.set_state(Form.request_text)
    await callback.message.answer(
        "Укажите, по каким вопросам или датам вы можете помочь:"
    )
    await callback.answer()

@dp.message(Form.request_text, F.text)
async def process_partial_accept(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = db_requests[request_id]
    
    duty = db_users[message.from_user.id]
    request.duty_id = duty.id
    request.status = "partially_accepted"
    request.feedback = message.text
    
    leader = db_users[request.leader_id]
    
    await bot.send_message(
        chat_id=request.leader_id,
        text=(
            f"🔄 Ваш запрос частично принят\n\n"
            f"Дежурный по Москве:\n"
            f"👤 {duty.full_name}\n"
            f"📞 {duty.phone}\n"
            f"📱 @{duty.telegram_username}\n\n"
            f"Он может помочь вам с:\n"
            f"{message.text}\n\n"
            f"Свяжитесь с ним для уточнения деталей."
        ),
    )
    
    duty.guests_helped += 1
    
    await message.answer(
        "Лидер уведомлен о вашем частичном согласии.",
        reply_markup=await get_main_keyboard(duty),
    )
    await state.clear()

@dp.message(F.text == "Мои запросы")
async def show_my_requests(message: Message) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "leader":
        await message.answer("Эта функция доступна только для Лидеров России.")
        return
    
    my_requests = [r for r in db_requests.values() if r.leader_id == message.from_user.id]
    
    if not my_requests:
        await message.answer("У вас пока нет активных запросов.")
        return
    
    for request in my_requests:
        status_emoji = {
            "pending": "🕒",
            "accepted": "✅",
            "rejected": "❌",
            "partially_accepted": "🔄",
        }.get(request.status, "❓")
        
        text = (
            f"{status_emoji} Запрос #{request.id}\n"
            f"📅 Даты: {request.start_date} - {request.end_date}\n"
            f"📝 Запрос: {request.request_text}\n"
            f"Статус: {request.status}"
        )
        
        if request.duty_id:
            duty = db_users[request.duty_id]
            text += f"\n\nДежурный: {duty.full_name} (@{duty.telegram_username})"
        
        if request.status in ["accepted", "partially_accepted"] and not request.rating:
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="Оставить отзыв",
                    callback_data=f"feedback_{request.id}",
                )
            )
            await message.answer(
                text,
                reply_markup=builder.as_markup(),
            )
        else:
            await message.answer(text)

@dp.message(F.text == "Мои принятые запросы")
async def show_accepted_requests(message: Message) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "duty":
        await message.answer("Эта функция доступна только для Дежурных по Москве.")
        return
    
    my_requests = [r for r in db_requests.values() if r.duty_id == message.from_user.id]
    
    if not my_requests:
        await message.answer("Вы пока не приняли ни одного запроса.")
        return
    
    for request in my_requests:
        leader = db_users[request.leader_id]
        
        rating_text = ""
        if request.rating:
            rating_text = f"\n⭐ Оценка: {request.rating}/5"
            if request.feedback:
                rating_text += f"\n📝 Отзыв: {request.feedback}"
        
        text = (
            f"Запрос #{request.id}\n"
            f"👤 Лидер: {leader.full_name}\n"
            f"📅 Даты: {request.start_date} - {request.end_date}\n"
            f"📝 Запрос: {request.request_text}"
            f"{rating_text}"
        )
        
        await message.answer(text)

@dp.message(F.text == "Оставить отзыв")
async def leave_feedback(message: Message, state: FSMContext) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "leader":
        await message.answer("Эта функция доступна только для Лидеров России.")
        return
    
    rateable_requests = [
        r for r in db_requests.values() 
        if r.leader_id == message.from_user.id 
        and r.status in ["accepted", "partially_accepted"]
        and not r.rating
    ]
    
    if not rateable_requests:
        await message.answer("У вас нет запросов, готовых для оценки.")
        return
    
    builder = InlineKeyboardBuilder()
    for request in rateable_requests[:10]:
        builder.add(
            InlineKeyboardButton(
                text=f"Запрос #{request.id}",
                callback_data=f"rate_{request.id}",
            )
        )
    builder.adjust(1)
    
    await message.answer(
        "Выберите запрос для оценки:",
        reply_markup=builder.as_markup(),
    )

@dp.callback_query(F.data.startswith("rate_"))
async def rate_request(callback: types.CallbackQuery, state: FSMContext) -> None:
    request_id = int(callback.data.split("_")[1])
    request = db_requests.get(request_id)
    
    if not request:
        await callback.answer("Запрос не найден.")
        return
    
    if request.rating:
        await callback.answer("Этот запрос уже оценен.")
        return
    
    await state.update_data(request_id=request_id)
    await state.set_state(Form.rating)
    
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.add(InlineKeyboardButton(text=str(i), callback_data=f"stars_{i}"))
    builder.adjust(5)
    
    await callback.message.answer(
        "Оцените помощь Дежурного по Москве (1-5 звезд):",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("stars_"), Form.rating)
async def process_rating(callback: types.CallbackQuery, state: FSMContext) -> None:
    rating = int(callback.data.split("_")[1])
    data = await state.get_data()
    request_id = data["request_id"]
    request = db_requests[request_id]
    
    request.rating = rating
    await state.set_state(Form.feedback)
    
    await callback.message.answer(
        "Напишите ваш отзыв о работе Дежурного (или нажмите /skip чтобы пропустить):"
    )
    await callback.answer()

@dp.message(Form.feedback, F.text)
async def process_feedback_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = db_requests[request_id]
    
    request.feedback = message.text
    
    duty = db_users[request.duty_id]
    
    duty_requests = [r for r in db_requests.values() if r.duty_id == duty.id and r.rating]
    if duty_requests:
        duty.rating = sum(r.rating for r in duty_requests) / len(duty_requests)
    
    user = db_users[message.from_user.id]
    keyboard = await get_main_keyboard(user)
    
    await message.answer(
        "Спасибо за ваш отзыв! Он поможет улучшить сервис.",
        reply_markup=keyboard,
    )
    await state.clear()

@dp.message(Command("skip"), Form.feedback)
async def skip_feedback(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    request_id = data["request_id"]
    request = db_requests[request_id]
    
    duty = db_users[request.duty_id]
    
    duty_requests = [r for r in db_requests.values() if r.duty_id == duty.id and r.rating]
    if duty_requests:
        duty.rating = sum(r.rating for r in duty_requests) / len(duty_requests)
    
    user = db_users[message.from_user.id]
    keyboard = await get_main_keyboard(user)
    
    await message.answer(
        "Спасибо за оценку!",
        reply_markup=keyboard,
    )
    await state.clear()

@dp.message(F.text == "Мой профиль")
async def show_profile(message: Message) -> None:
    user = db_users.get(message.from_user.id)
    if not user or user.role != "duty":
        await message.answer("Эта функция доступна только для Дежурных по Москве.")
        return
    
    rating_text = f"⭐ Рейтинг: {user.rating:.1f}/5" if user.rating else "⭐ Рейтинг: пока нет оценок"
    
    text = (
        f"👤 Ваш профиль Дежурного\n\n"
        f"ФИО: {user.full_name}\n"
        f"Телефон: {user.phone}\n"
        f"Telegram: @{user.telegram_username}\n"
        f"Помогли гостям: {user.guests_helped} раз\n"
        f"{rating_text}"
    )
    
    await message.answer(text)

@dp.errors()
async def errors_handler(update: types.Update, exception: Exception):
    logger.error(f"Апдейт {update} вызвал ошибку {exception}")
    return True

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
