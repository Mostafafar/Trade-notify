import asyncio
from binance import AsyncClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingMonitorBot:
    def __init__(self):
        self.binance_client = None
        self.application = None
        self.monitoring_tasks = {}

    async def init_clients(self):
        """Initialize API clients"""
        self.binance_client = await AsyncClient.create()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        await update.message.reply_text(
            "👋 **ربات مانیتورینگ معاملات با اهرم**\n\n"
            "دستورات موجود:\n"
            "/set_coin - تنظیم ارز\n"
            "/set_leverage - تنظیم اهرم\n"
            "/set_alloc - تنظیم درصد سرمایه\n"
            "/set_target - تنظیم درصد تغییر هدف\n"
            "/start_monitor - شروع مانیتورینگ\n"
            "/stop_monitor - توقف مانیتورینگ",
            parse_mode='Markdown'
        )

    async def set_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set cryptocurrency to monitor"""
        context.user_data['waiting_for'] = 'coin'
        await update.message.reply_text("لطفاً نماد ارز را وارد کنید (مثلاً BTC یا ETH):")

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set leverage"""
        if 'coin' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا ارز را تنظیم کنید (/set_coin)")
            return
        context.user_data['waiting_for'] = 'leverage'
        await update.message.reply_text("لطفاً مقدار اهرم را وارد کنید (مثلاً 2 برای 2x):")

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set allocation percentage"""
        if 'leverage' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا اهرم را تنظیم کنید (/set_leverage)")
            return
        context.user_data['waiting_for'] = 'allocation'
        await update.message.reply_text("لطفاً درصد سرمایه را وارد کنید (مثلاً 50 برای 50%):")

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target percentage change"""
        if 'allocation' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا درصد سرمایه را تنظیم کنید (/set_alloc)")
            return
        context.user_data['waiting_for'] = 'target'
        await update.message.reply_text("لطفاً درصد تغییر هدف را وارد کنید (مثلاً 5 برای 5%):")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all text messages"""
        if 'waiting_for' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً از دستورات استفاده کنید")
            return

        waiting_for = context.user_data['waiting_for']
        text = update.message.text.strip()

        try:
            if waiting_for == 'coin':
                context.user_data['coin'] = f"{text.upper()}USDT"
                await update.message.reply_text(f"✅ ارز {text.upper()} تنظیم شد")
                await self.set_leverage(update, context)

            elif waiting_for == 'leverage':
                leverage = float(text)
                if not 1 <= leverage <= 125:
                    raise ValueError
                context.user_data['leverage'] = leverage
                await update.message.reply_text(f"✅ اهرم {leverage}x تنظیم شد")
                await self.set_allocation(update, context)

            elif waiting_for == 'allocation':
                alloc = float(text)
                if not 0 < alloc <= 100:
                    raise ValueError
                context.user_data['allocation'] = alloc
                await update.message.reply_text(f"✅ تخصیص {alloc}% تنظیم شد")
                await self.set_target(update, context)

            elif waiting_for == 'target':
                target = float(text)
                if target <= 0:
                    raise ValueError
                context.user_data['target_change'] = target
                await update.message.reply_text(
                    f"✅ تنظیمات کامل شد:\n\n"
                    f"🏷️ ارز: {context.user_data['coin']}\n"
                    f"📊 اهرم: {context.user_data['leverage']}x\n"
                    f"💰 تخصیص: {context.user_data['allocation']}%\n"
                    f"🎯 درصد تغییر هدف: {context.user_data['target_change']}%"
                )
                context.user_data.pop('waiting_for', None)

        except ValueError:
            await update.message.reply_text("⚠️ لطفاً مقدار معتبر وارد کنید")
            return

    async def get_current_price(self, context: ContextTypes.DEFAULT_TYPE):
        """Get current price of the coin"""
        try:
            ticker = await self.binance_client.get_symbol_ticker(
                symbol=context.user_data['coin']
            )
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"خطا در دریافت قیمت: {e}")
            return None

    async def monitor_task(self, user_id, context):
        """Background monitoring task"""
        while context.user_data.get('monitoring', False):
            try:
                current_price = await self.get_current_price(context)
                if current_price is None:
                    await asyncio.sleep(60)
                    continue
                
                last_price = context.user_data.get('last_price')
                if last_price is None:
                    context.user_data['last_price'] = current_price
                    await asyncio.sleep(60)
                    continue
                
                leverage = context.user_data['leverage']
                change = ((current_price - last_price) / last_price) * 100 * leverage
                
                if abs(change) >= context.user_data['target_change']:
                    direction = "📈 افزایش" if change > 0 else "📉 کاهش"
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🚨 اعلان تغییر قیمت 🚨\n\n"
                            f"🏷️ ارز: {context.user_data['coin']}\n"
                            f"{direction} {abs(change):.2f}% (با اهرم {leverage}x)\n"
                            f"💰 تخصیص: {context.user_data['allocation']}%\n\n"
                            f"قیمت قبلی: {last_price:.8f}\n"
                            f"قیمت فعلی: {current_price:.8f}"
                        )
                    )
                    context.user_data['last_price'] = current_price
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"خطا در مانیتورینگ: {e}")
                await asyncio.sleep(300)

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start monitoring"""
        user_id = update.effective_user.id
        if not all(key in context.user_data for key in ['coin', 'leverage', 'allocation', 'target_change']):
            await update.message.reply_text("⚠️ لطفاً ابتدا تمام تنظیمات را کامل کنید")
            return
        
        if context.user_data.get('monitoring'):
            await update.message.reply_text("⚠️ مانیتورینگ در حال اجراست")
            return

        context.user_data['monitoring'] = True
        context.user_data['last_price'] = await self.get_current_price(context)
        
        task = asyncio.create_task(self.monitor_task(user_id, context))
        self.monitoring_tasks[user_id] = task
        
        await update.message.reply_text(
            f"🔍 مانیتورینگ {context.user_data['coin']} شروع شد\n"
            f"هر تغییر {context.user_data['target_change']}% با اهرم {context.user_data['leverage']}x اطلاع داده می‌شود"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop monitoring"""
        user_id = update.effective_user.id
        if context.user_data.get('monitoring'):
            context.user_data['monitoring'] = False
            
            if user_id in self.monitoring_tasks:
                self.monitoring_tasks[user_id].cancel()
                try:
                    await self.monitoring_tasks[user_id]
                except asyncio.CancelledError:
                    pass
                del self.monitoring_tasks[user_id]
            
            await update.message.reply_text("⏹️ مانیتورینگ متوقف شد")
        else:
            await update.message.reply_text("⚠️ مانیتورینگ فعالی وجود ندارد")

async def run_bot():
    """Run the bot with proper event loop management"""
    monitor_bot = TradingMonitorBot()
    await monitor_bot.init_clients()
    
    application = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
    monitor_bot.application = application

    # Add handlers
    application.add_handler(CommandHandler("start", monitor_bot.start))
    application.add_handler(CommandHandler("set_coin", monitor_bot.set_coin))
    application.add_handler(CommandHandler("set_leverage", monitor_bot.set_leverage))
    application.add_handler(CommandHandler("set_alloc", monitor_bot.set_allocation))
    application.add_handler(CommandHandler("set_target", monitor_bot.set_target))
    application.add_handler(CommandHandler("start_monitor", monitor_bot.start_monitor))
    application.add_handler(CommandHandler("stop_monitor", monitor_bot.stop_monitor))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_bot.handle_message))

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("بات با موفقیت شروع به کار کرد")
        while True:
            await asyncio.sleep(3600)
            
    except asyncio.CancelledError:
        logger.info("دریافت سیگنال توقف...")
    except Exception as e:
        logger.error(f"خطای شدید: {e}", exc_info=True)
    finally:
        logger.info("در حال خاموش کردن ربات...")
        if hasattr(monitor_bot, 'application') and monitor_bot.application:
            await monitor_bot.application.stop()
            await monitor_bot.application.shutdown()
        if hasattr(monitor_bot, 'binance_client') and monitor_bot.binance_client:
            await monitor_bot.binance_client.close_connection()
        logger.info("ربات خاموش شد")

def main():
    """Main entry point that properly handles the event loop"""
    try:
        # Create a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the bot
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("دریافت سیگنال قطع (Ctrl+C)...")
    except Exception as e:
        logger.error(f"خطای غیرمنتظره: {e}", exc_info=True)
    finally:
        # Cleanup
        tasks = asyncio.all_tasks(loop=loop)
        for task in tasks:
            task.cancel()
        
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.info("حلقه رویداد بسته شد")

if __name__ == "__main__":
    main()
