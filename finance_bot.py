import asyncio
import os
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY')
GIGACHAT_SCOPE = os.getenv('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')
GIGACHAT_MODEL = os.getenv('GIGACHAT_MODEL', 'GigaChat')

# Системный промпт для финансового консультанта
SYSTEM_PROMPT = """Ты — профессиональный финансовый консультант для директора компании. Твоя задача — давать четкие, структурированные ответы на вопросы по финансам.

Правила:
1. Отвечай только по финансовой тематике (бюджетирование, налоги, инвестиции, управление денежным потоком, анализ затрат, финансовое планирование)
2. Если вопрос не по финансам — вежливо откажись
3. Используй структуру: "Суть вопроса" → "Рекомендация" → "Действия"
4. Ссылайся на реальные финансовые принципы и практики
5. Будь лаконичен, но информативен
6. Используй эмодзи для структурирования:
   📊 — для сути вопроса
   💡 — для рекомендации
   📋 — для действий
   ⚠️ — для предупреждений
   ✅ — для итогов

Формат ответа:
📊 Суть вопроса: [краткое описание]
💡 Рекомендация: [конкретный совет]
📋 Действия: [пошаговый план]
⚠️ Важно: [предостережения, если нужны]
✅ Итог: [резюме]"""


# Инициализация клиента GigaChat
def get_gigachat_client():
    """Создает и возвращает клиент GigaChat"""
    try:
        client = GigaChat(
            credentials=GIGACHAT_AUTH_KEY,
            scope=GIGACHAT_SCOPE,
            model=GIGACHAT_MODEL,
            verify_ssl_certs=False,
            timeout=60
        )
        return client
    except Exception as e:
        logger.error(f"Ошибка инициализации GigaChat: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    user = update.effective_user
    await update.message.reply_text(
        f"💰 Финансовый консультант\n\n"
        f"Здравствуйте, {user.first_name or user.username}!\n\n"
        f"Я — AI-консультант по финансам для директоров.\n\n"
        f"Я могу помочь с:\n"
        f"• 📊 Оптимизацией бюджета\n"
        f"• 📈 Финансовым планированием\n"
        f"• 💰 Анализом затрат\n"
        f"• 🏦 Оценкой инвестиций\n"
        f"• 🔄 Управлением денежным потоком\n"
        f"• 📑 Налоговой оптимизацией\n\n"
        f"Как задать вопрос: просто напишите его текстом.\n\n"
        f"Пример: «Как оптимизировать налоги для ООО?»\n\n"
        f"Я дам структурированный ответ с конкретными рекомендациями."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "📋 Справка\n\n"
        "Доступные команды:\n"
        "/start — приветствие и описание\n"
        "/help — эта справка\n\n"
        "Как задать вопрос:\n"
        "Просто напишите текст — я отвечу как финансовый консультант.\n\n"
        "Примеры вопросов:\n"
        "• Как рассчитать точку безубыточности?\n"
        "• Как снизить издержки производства?\n"
        "• Что такое EBITDA и как его считать?\n"
        "• Как оценить эффективность инвестиций (ROI)?"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений через GigaChat"""
    user_message = update.message.text
    user_id = update.effective_user.id

    # Показываем, что бот печатает
    await update.message.chat.send_action(action="typing")

    try:
        # Получаем клиент GigaChat
        client = get_gigachat_client()
        if not client:
            await update.message.reply_text(
                "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже."
            )
            return

        # Формируем запрос в правильном формате
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
                Messages(role=MessagesRole.USER, content=user_message)
            ],
            temperature=0.7,
            max_tokens=1500,
            repetition_penalty=1.1
        )

        # Отправляем запрос к GigaChat
        response = client.chat(payload)

        # Получаем ответ
        answer = response.choices[0].message.content

        # Проверяем, что ответ не пустой
        if not answer or len(answer.strip()) == 0:
            answer = "Извините, не удалось сформировать ответ. Попробуйте переформулировать вопрос."

        # Отправляем ответ
        await update.message.reply_text(answer)

        # Логируем для отладки
        logger.info(f"Пользователь {user_id}: {user_message[:50]}... -> Ответ получен")

    except Exception as e:
        logger.error(f"Ошибка при запросе к GigaChat: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.\n\n"
            "Возможные причины:\n"
            "• Проблемы с подключением к GigaChat API\n"
            "• Превышение лимитов токенов\n"
            "• Неверный формат запроса"
        )


async def main():
    """Запуск бота"""
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    print("🤖 Финансовый консультант (GigaChat) запущен!")
    print(f"Модель: {GIGACHAT_MODEL}")
    print(f"Сфера: {GIGACHAT_SCOPE}")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Держим бота запущенным
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Остановка...")