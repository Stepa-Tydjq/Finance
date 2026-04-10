import asyncio
import os
import logging
from datetime import datetime
from collections import defaultdict

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

# Максимальное количество сообщений в истории диалога
MAX_DIALOG_HISTORY = 4

# Словарь для хранения клиентов GigaChat по user_id
gigachat_clients = {}

# Словарь для хранения истории диалогов по user_id
# Каждый диалог — список последних N сообщений
dialog_histories = defaultdict(list)

# Системный промпт для финансового консультанта
SYSTEM_PROMPT = """Ты — профессиональный финансовый консультант для директора компании. Твоя задача — давать четкие, структурированные ответы на вопросы по финансам.

Правила:
1. Отвечай ТОЛЬКО по финансовой тематике (бюджетирование, налоги, инвестиции, управление денежным потоком, анализ затрат, финансовое планирование, бухгалтерия, кредиты, банковские продукты для бизнеса)
2. Если вопрос не по финансам — ответь: "⚠️ Я специализируюсь только на финансовых вопросах для бизнеса. Пожалуйста, задайте вопрос, связанный с финансами, бюджетированием, налогами, инвестициями или управлением денежным потоком."
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

# Промпт для проверки тематики вопроса
TOPIC_CHECK_PROMPT = """Определи, относится ли следующий вопрос к финансовой тематике для бизнеса.
Тематика включает: бюджетирование, налоги, инвестиции, управление денежным потоком, анализ затрат, финансовое планирование, бухгалтерия, кредиты, банковские продукты для бизнеса, финансовая аналитика, оптимизация расходов.

Вопрос: {question}

Ответь только "YES" если вопрос относится к финансовой тематике, или "NO" если не относится."""


def get_or_create_gigachat_client(user_id: int):
    """Возвращает или создает отдельный клиент GigaChat для каждого пользователя"""
    if user_id not in gigachat_clients:
        try:
            client = GigaChat(
                credentials=GIGACHAT_AUTH_KEY,
                scope=GIGACHAT_SCOPE,
                model=GIGACHAT_MODEL,
                verify_ssl_certs=False,
                timeout=60
            )
            gigachat_clients[user_id] = client
            logger.info(f"Создан новый клиент GigaChat для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Ошибка инициализации GigaChat для пользователя {user_id}: {e}")
            return None
    return gigachat_clients[user_id]


async def check_topic_relevance(client, question: str) -> bool:
    """Проверяет, относится ли вопрос к финансовой тематике"""
    try:
        payload = Chat(
            messages=[
                Messages(
                    role=MessagesRole.SYSTEM,
                    content=TOPIC_CHECK_PROMPT.format(question=question)
                )
            ],
            temperature=0.1,  # Низкая температура для точного ответа
            max_tokens=10
        )

        response = client.chat(payload)
        answer = response.choices[0].message.content.strip().upper()

        return "YES" in answer

    except Exception as e:
        logger.error(f"Ошибка при проверке тематики: {e}")
        # В случае ошибки пропускаем вопрос (лучше перестраховаться)
        return True


def update_dialog_history(user_id: int, user_message: str, bot_response: str):
    """Обновляет историю диалога для пользователя (максимум 4 последних запроса)"""
    history = dialog_histories[user_id]

    # Добавляем новое сообщение и ответ
    history.append({
        "user": user_message,
        "bot": bot_response
    })

    # Оставляем только последние 4 сообщения
    if len(history) > MAX_DIALOG_HISTORY:
        dialog_histories[user_id] = history[-MAX_DIALOG_HISTORY:]
        logger.info(f"История диалога для пользователя {user_id} сокращена до {MAX_DIALOG_HISTORY} сообщений")


def build_context_messages(user_id: int) -> list:
    """Строит список сообщений с учетом истории диалога"""
    history = dialog_histories[user_id]
    context_messages = []

    for entry in history:
        context_messages.append(Messages(role=MessagesRole.USER, content=entry["user"]))
        context_messages.append(Messages(role=MessagesRole.ASSISTANT, content=entry["bot"]))

    return context_messages


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
    user_id = update.effective_user.id
    history_count = len(dialog_histories.get(user_id, []))

    await update.message.reply_text(
        "📋 Справка\n\n"
        "Доступные команды:\n"
        "/start — приветствие и описание\n"
        "/help — эта справка\n"
        "/clear — очистить историю диалога\n\n"
        "Как задать вопрос:\n"
        "Просто напишите текст — я отвечу как финансовый консультант.\n\n"
        "Примеры вопросов:\n"
        "• Как рассчитать точку безубыточности?\n"
        "• Как снизить издержки производства?\n"
        "• Что такое EBITDA и как его считать?\n"
        "• Как оценить эффективность инвестиций (ROI)?\n\n"
        f"📊 Текущая история диалога: {history_count}/{MAX_DIALOG_HISTORY} сообщ."
    )


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистка истории диалога для пользователя"""
    user_id = update.effective_user.id

    if user_id in dialog_histories:
        dialog_histories[user_id] = []
        logger.info(f"История диалога для пользователя {user_id} очищена")

    await update.message.reply_text(
        "🧹 История диалога очищена.\n\n"
        "Теперь я буду отвечать на вопросы без учета предыдущих сообщений."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщений через GigaChat с проверкой тематики и контекстом диалога"""
    user_message = update.message.text
    user_id = update.effective_user.id

    # Показываем, что бот печатает
    await update.message.chat.send_action(action="typing")

    try:
        # Получаем или создаем клиент GigaChat для пользователя
        client = get_or_create_gigachat_client(user_id)
        if not client:
            await update.message.reply_text(
                "⚠️ Сервис временно недоступен. Пожалуйста, попробуйте позже."
            )
            return

        # Проверяем тематику вопроса
        is_finance_topic = await check_topic_relevance(client, user_message)
        if not is_finance_topic:
            await update.message.reply_text(
                "⚠️ Я специализируюсь только на финансовых вопросах для бизнеса.\n\n"
                "Пожалуйста, задайте вопрос, связанный с:\n"
                "• 📊 Бюджетированием и планированием\n"
                "• 💰 Налоговой оптимизацией\n"
                "• 📈 Инвестициями и оценкой проектов\n"
                "• 🔄 Управлением денежным потоком\n"
                "• 📋 Анализом затрат и оптимизацией расходов"
            )
            logger.info(f"Пользователь {user_id}: запрос отклонен (не финансовая тематика)")
            return

        # Строим контекст диалога с учетом истории
        context_messages = build_context_messages(user_id)

        # Формируем запрос в правильном формате
        all_messages = [
            Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
            *context_messages,  # Добавляем историю диалога
            Messages(role=MessagesRole.USER, content=user_message)
        ]

        payload = Chat(
            messages=all_messages,
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

        # Обновляем историю диалога
        update_dialog_history(user_id, user_message, answer)

        # Отправляем ответ
        await update.message.reply_text(answer)

        # Логируем для отладки
        logger.info(f"Пользователь {user_id}: {user_message[:50]}... -> Ответ получен (история: {len(dialog_histories[user_id])} сообщ.)")

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
    app.add_handler(CommandHandler("clear", clear_history))
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