import asyncio
from binance import AsyncClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
import logging
import warnings
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Conversation states
WAITING_COIN, WAITING_LEVERAGE, WAITING_ALLOCATION, WAITING_TARGET = range(4)

class TradingMonitorBot:
    def __init__(self):
        self.user_data: Dict[int, dict] = {}
        self.binance_client: Optional[AsyncClient] = None
        self.monitoring_tasks: Dict[int, asyncio.Task] = {}
        self.application: Optional[Application] = None
        self._should_stop = asyncio.Event()
        self._polling_task: Optional[asyncio.Task] = None

    async def init_clients(self, api_key=None, api_secret=None):
        """Initialize API clients"""
        self.binance_client = await AsyncClient.create(api_key, api_secret)
        return self

    async def cleanup(self):
        """Cleanup resources properly"""
        # Cancel all monitoring tasks
        for user_id, task in self.monitoring_tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self.monitoring_tasks.clear()
        
        # Close Binance client
        if self.binance_client:
            await self.binance_client.close_connection()
            self.binance_client = None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        await update.message.reply_text(
            "👋 **ربات مانیتورینگ معاملات**\n\n"
            "دستورات موجود:\n"
            "/set_coin - تنظیم ارز دیجیتال\n"
            "/set_leverage - تنظیم اهرم\n"
            "/set_alloc - تنظیم درصد سرمایه\n" 
            "/set_target - تنظیم درصد تغییر هدف\n"
            "/start_monitor - شروع مانیتورینگ\n"
            "/stop_monitor - توقف مانیتورینگ\n"
            "/status - نمایش وضعیت فعلی",
            parse_mode='Markdown'
        )

    async def set_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set cryptocurrency to monitor"""
        await update.message.reply_text("لطفاً نماد ارز را وارد کنید (مثال: BTC یا ETH):")
        return WAITING_COIN

    async def process_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process coin input"""
        coin = update.message.text.upper()
        if not coin.isalpha():
            await update.message.reply_text("⚠️ لطفاً فقط حروف انگلیسی وارد کنید (مثال: BTC)")
            return WAITING_COIN
            
        user_id = update.effective_user.id
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
            
        self.user_data[user_id]['coin'] = f"{coin}USDT"
        await update.message.reply_text(
            f"✅ ارز {coin} تنظیم شد\n"
            f"لطفاً اهرم را با دستور /set_leverage تنظیم کنید"
        )
        return ConversationHandler.END

    # [Other methods remain the same as in previous complete implementation...]

async def run_bot():
    """Run the bot with proper resource management"""
    bot = TradingMonitorBot()
    
    try:
        # Initialize clients
        await bot.init_clients()
        
        # Create application
        application = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
        bot.application = application
        
        # Add handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("status", bot.status))
        application.add_handler(CommandHandler("set_leverage", bot.set_leverage)) 
        application.add_handler(CommandHandler("set_alloc", bot.set_allocation))
        application.add_handler(CommandHandler("set_target", bot.set_target))
        application.add_handler(CommandHandler("start_monitor", bot.start_monitor))
        application.add_handler(CommandHandler("stop_monitor", bot.stop_monitor))

        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('set_coin', bot.set_coin)],
            states={
                WAITING_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_coin)],
                WAITING_LEVERAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_leverage)],
                WAITING_ALLOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_allocation)],
                WAITING_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_target)],
            },
            fallbacks=[]
        )
        application.add_handler(conv_handler)

        # Run polling in background
        bot._polling_task = asyncio.create_task(application.run_polling())
        
        # Wait until shutdown is requested
        await bot._should_stop.wait()
        
    except asyncio.CancelledError:
        logger.info("توقف توسط کاربر")
    except Exception as e:
        logger.error(f"خطا در بات: {str(e)}", exc_info=True)
    finally:
        try:
            # Shutdown application if it exists
            if bot.application and bot.application.running:
                await bot.application.stop()
                await bot.application.shutdown()
            
            # Cleanup other resources
            await bot.cleanup()
            
        except Exception as e:
            logger.error(f"خطا در تمیزکاری: {str(e)}", exc_info=True)

def main():
    """Main entry point"""
    # Create and set new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run the bot
        main_task = loop.create_task(run_bot())
        loop.run_until_complete(main_task)
        
    except KeyboardInterrupt:
        logger.info("توقف بات با کیبورد")
    except Exception as e:
        logger.error(f"خطای حیاتی: {str(e)}", exc_info=True)
    finally:
        # Get all pending tasks
        pending = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        
        # Cancel all pending tasks
        for task in pending:
            task.cancel()
        
        # Run loop until all tasks are cancelled
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        
        # Close the loop
        loop.close()
        logger.info("بات با موفقیت خاموش شد")

if __name__ == "__main__":
    main()
