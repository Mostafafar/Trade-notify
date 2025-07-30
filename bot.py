import asyncio
import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
import logging
from typing import Dict

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingMonitorBot:
    def __init__(self):
        self.session = None
        self.application = None
        self.monitoring_tasks: Dict[int, asyncio.Task] = {}
        self.base_url = "https://api.kucoin.com"

    async def init_session(self):
        """Initialize aiohttp session"""
        self.session = aiohttp.ClientSession()

    async def get_kucoin_price(self, symbol: str) -> float:
        """Get current price from Kucoin API"""
        url = f"{self.base_url}/api/v1/market/orderbook/level1?symbol={symbol}"
        try:
            async with self.session.get(url) as response:
                data = await response.json()
                if data.get('code') == '200000' and data.get('data'):
                    return float(data['data']['price'])
                logger.error(f"خطا در دریافت قیمت از کوکوین: {data}")
                return None
        except Exception as e:
            logger.error(f"خطا در اتصال به کوکوین: {e}")
            return None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال پیام خوشآمدگویی"""
        await update.message.reply_text(
            "👋 **ربات مانیتورینگ معاملات با اهرم (با کوکوین)**\n\n"
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
        """تنظیم ارز برای مانیتورینگ"""
        context.user_data['waiting_for'] = 'coin'
        await update.message.reply_text("لطفاً نماد ارز را وارد کنید (مثلاً BTC یا ETH):")

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم اهرم"""
        if 'coin' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا ارز را تنظیم کنید (/set_coin)")
            return
        context.user_data['waiting_for'] = 'leverage'
        await update.message.reply_text("لطفاً مقدار اهرم را وارد کنید (مثلاً 2 برای 2x):")

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم درصد سرمایه"""
        if 'leverage' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا اهرم را تنظیم کنید (/set_leverage)")
            return
        context.user_data['waiting_for'] = 'allocation'
        await update.message.reply_text("لطفاً درصد سرمایه را وارد کنید (مثلاً 50 برای 50%):")

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم درصد تغییر هدف"""
        if 'allocation' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا درصد سرمایه را تنظیم کنید (/set_alloc)")
            return
        context.user_data['waiting_for'] = 'target'
        await update.message.reply_text("لطفاً درصد تغییر هدف را وارد کنید (مثلاً 5 برای 5%):")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش پیام‌های متنی"""
        if 'waiting_for' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً از دستورات استفاده کنید")
            return

        text = update.message.text.strip().upper()
        waiting_for = context.user_data['waiting_for']

        try:
            if waiting_for == 'coin':
                # بررسی وجود جفت ارز در کوکوین
                price = await self.get_kucoin_price(f"{text}-USDT")
                if price is None:
                    await update.message.reply_text(f"⚠️ ارز {text} در کوکوین یافت نشد")
                    return
                
                context.user_data['coin'] = f"{text}-USDT"
                await update.message.reply_text(f"✅ ارز {text} تنظیم شد (قیمت فعلی: {price:.2f}$)")
                await self.set_leverage(update, context)

            elif waiting_for == 'leverage':
                leverage = float(text)
                if not 1 <= leverage <= 100:
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
                
                # دریافت قیمت فعلی برای نمایش
                price = await self.get_kucoin_price(context.user_data['coin'])
                await update.message.reply_text(
                    f"✅ تنظیمات کامل شد:\n\n"
                    f"🏷️ ارز: {context.user_data['coin']}\n"
                    f"📊 اهرم: {context.user_data['leverage']}x\n"
                    f"💰 تخصیص: {context.user_data['allocation']}%\n"
                    f"🎯 درصد تغییر هدف: {context.user_data['target_change']}%\n"
                    f"💵 قیمت فعلی: {price:.2f}$"
                )
                context.user_data.pop('waiting_for', None)

        except ValueError:
            await update.message.reply_text("⚠️ لطفاً مقدار معتبر وارد کنید")
            return

    async def monitor_task(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """وظیفه مانیتورینگ در پس‌زمینه"""
        while context.user_data.get('monitoring', False):
            try:
                current_price = await self.get_kucoin_price(context.user_data['coin'])
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
                            f"قیمت قبلی: {last_price:.2f}$\n"
                            f"قیمت فعلی: {current_price:.2f}$"
                        )
                    )
                    context.user_data['last_price'] = current_price
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"خطا در مانیتورینگ: {e}")
                await asyncio.sleep(300)

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع مانیتورینگ"""
        user_id = update.effective_user.id
        required_keys = ['coin', 'leverage', 'allocation', 'target_change']
        
        if not all(key in context.user_data for key in required_keys):
            await update.message.reply_text("⚠️ لطفاً ابتدا تمام تنظیمات را کامل کنید")
            return
        
        if context.user_data.get('monitoring'):
            await update.message.reply_text("⚠️ مانیتورینگ در حال اجراست")
            return

        context.user_data['monitoring'] = True
        context.user_data['last_price'] = await self.get_kucoin_price(context.user_data['coin'])
        
        task = asyncio.create_task(self.monitor_task(user_id, context))
        self.monitoring_tasks[user_id] = task
        
        await update.message.reply_text(
            f"🔍 مانیتورینگ {context.user_data['coin']} شروع شد\n"
            f"هر تغییر {context.user_data['target_change']}% با اهرم {context.user_data['leverage']}x اطلاع داده می‌شود"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """توقف مانیتورینگ"""
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
    """اجرای اصلی بات"""
    bot = TradingMonitorBot()
    await bot.init_session()
    
    application = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
    bot.application = application

    # افزودن دستورات
    handlers = [
        CommandHandler("start", bot.start),
        CommandHandler("set_coin", bot.set_coin),
        CommandHandler("set_leverage", bot.set_leverage),
        CommandHandler("set_alloc", bot.set_allocation),
        CommandHandler("set_target", bot.set_target),
        CommandHandler("start_monitor", bot.start_monitor),
        CommandHandler("stop_monitor", bot.stop_monitor),
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

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
        if hasattr(bot, 'application') and bot.application:
            await bot.application.stop()
            await bot.application.shutdown()
        if hasattr(bot, 'session') and bot.session:
            await bot.session.close()
        logger.info("ربات خاموش شد")

def main():
    """ورودی اصلی برنامه"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("دریافت سیگنال قطع (Ctrl+C)...")
    except Exception as e:
        logger.error(f"خطای غیرمنتظره: {e}", exc_info=True)
    finally:
        tasks = asyncio.all_tasks(loop=loop)
        for task in tasks:
            task.cancel()
        
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.info("حلقه رویداد بسته شد")

if __name__ == "__main__":
    main()
