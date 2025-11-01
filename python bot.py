import os
import asyncio
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ В файле .env не найден BOT_TOKEN!")

# =============== Стартовая функция ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔮 Получить гороскоп", callback_data="get_horoscope")],
    ]
    await update.message.reply_text(
        "✨ Добро пожаловать в AstroLuna Advanced!\n\n"
        "Я помогу рассчитать твой персональный гороскоп по дате, времени и городу рождения 🌙",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# =============== Обработка кнопок ===============
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "get_horoscope":
        await query.message.reply_text("📅 Введи свою дату рождения (в формате ДД.ММ.ГГГГ):")
        context.user_data["step"] = "date"
        return

# =============== Получение данных от пользователя ===============
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "date":
        context.user_data["date"] = update.message.text
        context.user_data["step"] = "time"
        await update.message.reply_text("⏰ Теперь введи время рождения (например, 14:35):")

    elif step == "time":
        context.user_data["time"] = update.message.text
        context.user_data["step"] = "city"
        await update.message.reply_text("🏙️ Укажи город рождения:")

    elif step == "city":
        context.user_data["city"] = update.message.text
        await show_result(update, context)

# =============== Формирование результата ===============
async def show_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = context.user_data.get("date")
    time = context.user_data.get("time")
    city = context.user_data.get("city")

    result = (
        f"🌟 Твои данные:\n\n"
        f"📅 Дата рождения: {date}\n"
        f"⏰ Время рождения: {time}\n"
        f"🏙️ Город: {city}\n\n"
        f"🔮 Расчёт гороскопа завершён!\n"
        f"(В демо версии анализ символический)"
    )

    keyboard = [
        [InlineKeyboardButton("🧠 Получить расширенный анализ", callback_data="get_advanced")],
        [InlineKeyboardButton("🔁 Заполнить заново", callback_data="get_horoscope")],
    ]

    await update.message.reply_text(result, reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data.clear()

# =============== Запуск бота ===============
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ AstroLuna Advanced запущен!")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())