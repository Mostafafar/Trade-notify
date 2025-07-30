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
        self.user_data = {}
        self.binance_client = None
        self.bot = None
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
        await update.message.reply_text("لطفا نماد ارز را وارد کنید (مثلا BTC یا ETH):")
        context.user_data['waiting_for'] = 'coin'
        return

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set leverage"""
        await update.message.reply_text("لطفا مقدار اهرم را وارد کنید (مثلا 2 برای 2x):")
        context.user_data['waiting_for'] = 'leverage'
        return

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set allocation percentage"""
        await update.message.reply_text("لطفا درصد سرمایه را وارد کنید (مثلا 50 برای 50%):")
        context.user_data['waiting_for'] = 'allocation'
        return

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target percentage change"""
        await update.message.reply_text("لطفا درصد تغییر هدف را وارد کنید (مثلا 5 برای 5%):")
        context.user_data['waiting_for'] = 'target'
        return

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all text messages"""
        if 'waiting_for' not in context.user_data:
            return

        user_id = update.effective_user.id
        text = update.message.text.upper()
        waiting_for = context.user_data['waiting_for']

        try:
            if waiting_for == 'coin':
                self.user_data[user_id] = {
                    'coin': f"{text}USDT",
                    'leverage': 1,
                    'allocation': 100,
                    'target_change': 5,
                    'monitoring': False
                }
                await update.message.reply_text(f"✅ ارز {text} تنظیم شد")
                await self.set_leverage(update, context)

            elif waiting_for == 'leverage':
                leverage = float(text)
                if leverage < 1 or leverage > 125:
                    raise ValueError
                self.user_data[user_id]['leverage'] = leverage
                await update.message.reply_text(f"✅ اهرم {leverage}x تنظیم شد")
                await self.set_allocation(update, context)

            elif waiting_for == 'allocation':
                alloc = float(text)
                if alloc <= 0 or alloc > 100:
                    raise ValueError
                self.user_data[user_id]['allocation'] = alloc
                await update.message.reply_text(f"✅ تخصیص {alloc}% تنظیم شد")
                await self.set_target(update, context)

            elif waiting_for == 'target':
                target = float(text)
                if target <= 0:
                    raise ValueError
                self.user_data[user_id]['target_change'] = target
                user_data = self.user_data[user_id]
                await update.message.reply_text(
                    f"✅ تنظیمات کامل شد:\n\n"
                    f"🏷️ ارز: {user_data['coin']}\n"
                    f"📊 اهرم: {user_data['leverage']}x\n"
                    f"💰 تخصیص: {user_data['allocation']}%\n"
                    f"🎯 درصد تغییر هدف: {user_data['target_change']}%"
                )
                context.user_data.pop('waiting_for', None)

        except ValueError:
            await update.message.reply_text("⚠️ لطفا مقدار معتبر وارد کنید")
            return

    async def get_current_price(self, user_id):
        """Get current price of the coin"""
        try:
            ticker = await self.binance_client.get_symbol_ticker(
                symbol=self.user_data[user_id]['coin']
            )
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"خطا در دریافت قیمت: {e}")
            return None

    async def monitor_task(self, user_id):
        """Background monitoring task"""
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
                
                leverage = self.user_data[user_id]['leverage']
                change = ((current_price - last_price) / last_price) * 100 * leverage
                
                if abs(change) >= self.user_data[user_id]['target_change']:
                    direction = "📈 افزایش" if change > 0 else "📉 کاهش"
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🚨 اعلان تغییر قیمت 🚨\n\n"
                            f"🏷️ ارز: {self.user_data[user_id]['coin']}\n"
                            f"{direction} {abs(change):.2f}% (با اهرم {leverage}x)\n"
                            f"💰 تخصیص: {self.user_data[user_id]['allocation']}%\n\n"
                            f"قیمت قبلی: {last_price:.8f}\n"
                            f"قیمت فعلی: {current_price:.8f}"
                        )
                    )
                    self.user_data[user_id]['last_price'] = current_price
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"خطا در مانیتورینگ: {e}")
                await asyncio.sleep(300)

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start monitoring"""
        user_id = update.effective_user.id
        if user_id not in self.user_data:
            await update.message.reply_text("⚠️ لطفا ابتدا تنظیمات را کامل کنید")
            return
        
        if self.user_data[user_id].get('monitoring'):
            await update.message.reply_text("⚠️ مانیتورینگ در حال اجراست")
            return

        self.user_data[user_id]['monitoring'] = True
        self.user_data[user_id]['last_price'] = await self.get_current_price(user_id)
        
        task = asyncio.create_task(self.monitor_task(user_id))
        self.monitoring_tasks[user_id] = task
        
        await update.message.reply_text(
            f"🔍 مانیتورینگ {self.user_data[user_id]['coin']} شروع شد\n"
            f"هر تغییر {self.user_data[user_id]['target_change']}% با اهرم {self.user_data[user_id]['leverage']}x اطلاع داده می‌شود"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop monitoring"""
        user_id = update.effective_user.id
        if user_id in self.user_data and self.user_data[user_id].get('monitoring'):
            self.user_data[user_id]['monitoring'] = False
            
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

async def main():
    """Main application"""
    monitor_bot = TradingMonitorBot()
    await monitor_bot.init_clients()
    
    application = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
    monitor_bot.bot = application.bot

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
        
        logger.info("ربات با موفقیت شروع به کار کرد")
        while True:
            await asyncio.sleep(3600)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"خطای شدید: {e}", exc_info=True)
    finally:
        logger.info("در حال خاموش کردن ربات...")
        if application.updater:
            await application.updater.stop()
        if application:
            await application.stop()
            await application.shutdown()
        if monitor_bot.binance_client:
            await monitor_bot.binance_client.close_connection()
        logger.info("ربات خاموش شد")

if __name__ == "__main__":
    asyncio.run(main())
