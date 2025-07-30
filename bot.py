import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("دستور start اجرا شد")
    await update.message.reply_text("بات شروع شد!")

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("دستور test اجرا شد")
    await update.message.reply_text("دستور تست کار کرد!")

async def main():
    app = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    logger.info("بات شروع شد")
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
