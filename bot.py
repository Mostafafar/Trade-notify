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

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set leverage"""
        await update.message.reply_text("لطفاً مقدار اهرم را وارد کنید (بین 1 تا 125):")
        return WAITING_LEVERAGE

    async def process_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process leverage input"""
        try:
            leverage = float(update.message.text)
            if leverage < 1 or leverage > 125:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['leverage'] = leverage
            await update.message.reply_text(
                f"✅ اهرم {leverage}x تنظیم شد\n"
                f"لطفاً درصد سرمایه را با دستور /set_alloc تنظیم کنید"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ لطفاً یک عدد معتبر بین 1 تا 125 وارد کنید")
            return WAITING_LEVERAGE

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set allocation percentage"""
        await update.message.reply_text("لطفاً درصد سرمایه را وارد کنید (بین 0.1 تا 100):")
        return WAITING_ALLOCATION

    async def process_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process allocation input"""
        try:
            alloc = float(update.message.text)
            if alloc <= 0 or alloc > 100:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['allocation'] = alloc
            await update.message.reply_text(
                f"✅ تخصیص {alloc}% تنظیم شد\n"
                f"لطفاً درصد تغییر هدف را با دستور /set_target تنظیم کنید"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ لطفاً یک عدد معتبر بین 0.1 تا 100 وارد کنید")
            return WAITING_ALLOCATION

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target percentage"""
        await update.message.reply_text("لطفاً درصد تغییر هدف را وارد کنید (مثال: 5 برای 5%):")
        return WAITING_TARGET

    async def process_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process target input"""
        try:
            target = float(update.message.text)
            if target <= 0:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['target_change'] = target
            
            await update.message.reply_text(
                f"✅ تنظیمات کامل شد:\n\n"
                f"🏷️ ارز: {self.user_data[user_id]['coin']}\n"
                f"📊 اهرم: {self.user_data[user_id].get('leverage', 1)}x\n"
                f"💰 تخصیص: {self.user_data[user_id].get('allocation', 100)}%\n"
                f"🎯 درصد تغییر هدف: {self.user_data[user_id].get('target_change', 5)}%\n\n"
                f"برای شروع مانیتورینگ از دستور /start_monitor استفاده کنید"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ لطفاً یک عدد معتبر بزرگتر از 0 وارد کنید")
            return WAITING_TARGET

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start price monitoring"""
        user_id = update.effective_user.id
        if user_id not in self.user_data or 'coin' not in self.user_data[user_id]:
            await update.message.reply_text("⚠️ لطفاً ابتدا ارز را با دستور /set_coin تنظیم کنید")
            return
            
        if user_id in self.monitoring_tasks and not self.monitoring_tasks[user_id].done():
            await update.message.reply_text("ℹ️ مانیتورینگ از قبل فعال است")
            return
            
        self.user_data[user_id]['monitoring'] = True
        current_price = await self.get_current_price(user_id)
        if current_price is None:
            await update.message.reply_text("⚠️ خطا در دریافت قیمت اولیه")
            return
            
        self.user_data[user_id]['last_price'] = current_price
        self.monitoring_tasks[user_id] = asyncio.create_task(self.monitor_price(user_id, context))
        
        await update.message.reply_text(
            f"🔍 مانیتورینگ {self.user_data[user_id]['coin']} شروع شد\n"
            f"هر تغییر {self.user_data[user_id].get('target_change', 5)}% "
            f"با اهرم {self.user_data[user_id].get('leverage', 1)}x به شما اطلاع داده می‌شود"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop price monitoring"""
        user_id = update.effective_user.id
        if user_id in self.monitoring_tasks:
            self.monitoring_tasks[user_id].cancel()
            try:
                await self.monitoring_tasks[user_id]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[user_id]
            
        if user_id in self.user_data:
            self.user_data[user_id]['monitoring'] = False
            
        await update.message.reply_text("⏹️ مانیتورینگ متوقف شد")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current status"""
        user_id = update.effective_user.id
        if user_id not in self.user_data or 'coin' not in self.user_data[user_id]:
            await update.message.reply_text("⚠️ هنوز تنظیماتی انجام نشده است")
            return
            
        user_data = self.user_data[user_id]
        monitoring_status = "فعال ✅" if user_data.get('monitoring', False) else "غیرفعال ❌"
        
        try:
            current_price = await self.get_current_price(user_id)
            price_info = f"قیمت فعلی: {current_price:.8f}"
        except Exception:
            price_info = "قیمت فعلی: نامعلوم"
        
        await update.message.reply_text(
            f"📊 وضعیت فعلی:\n\n"
            f"🏷️ ارز: {user_data['coin']}\n"
            f"📊 اهرم: {user_data.get('leverage', 1)}x\n"
            f"💰 تخصیص: {user_data.get('allocation', 100)}%\n"
            f"🎯 درصد تغییر هدف: {user_data.get('target_change', 5)}%\n"
            f"🔍 وضعیت مانیتورینگ: {monitoring_status}\n"
            f"{price_info}"
        )

    async def get_current_price(self, user_id):
        """Get current coin price"""
        try:
            ticker = await self.binance_client.get_symbol_ticker(
                symbol=self.user_data[user_id]['coin']
            )
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"خطا در دریافت قیمت برای کاربر {user_id}: {e}")
            return None

    async def monitor_price(self, user_id, context):
        """Monitor price changes"""
        while self.user_data.get(user_id, {}).get('monitoring', False):
            try:
                current_price = await self.get_current_price(user_id)
                if current_price is None:
                    await asyncio.sleep(60)
                    continue
                
                last_price = self.user_data[user_id].get('last_price')
                if last_price is None:
                    self.user_data[user_id]['last_price'] = current_price
                    await asyncio.sleep(60)
                    continue
                
                leverage = self.user_data[user_id].get('leverage', 1)
                change = ((current_price - last_price) / last_price) * 100 * leverage
                target_change = self.user_data[user_id].get('target_change', 5)
                
                if abs(change) >= target_change:
                    direction = "📈 افزایش" if change > 0 else "📉 کاهش"
                    allocation = self.user_data[user_id].get('allocation', 100)
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🚨 اعلان تغییر قیمت با اهرم 🚨\n\n"
                            f"🏷️ ارز: {self.user_data[user_id]['coin']}\n"
                            f"{direction} {abs(change):.2f}% (با اهرم {leverage}x)\n"
                            f"💰 تخصیص سرمایه: {allocation}%\n\n"
                            f"قیمت قبلی: {last_price:.8f}\n"
                            f"قیمت فعلی: {current_price:.8f}"
                        )
                    )
                    self.user_data[user_id]['last_price'] = current_price
                
                await asyncio.sleep(60)  # چک هر دقیقه
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"خطا در مانیتورینگ برای کاربر {user_id}: {e}")
                await asyncio.sleep(300)

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
