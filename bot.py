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
        logger.info(f"دریافت دستور start از کاربر {update.effective_user.id}")
        await update.message.reply_text(
            "👋 **ربات مانیتورینگ معاملات با اهرم (با کوکوین)**\n\n"
            "دستورات موجود:\n"
            "/set_coin - تنظیم ارز\n"
            "/set_leverage - تنظیم اهرم\n"
            "/set_alloc - تنظیم درصد سرمایه\n"
            "/set_target - تنظیم درصد تغییر هدف\n"
            "/start_monitor - شروع مانیتورینگ\n"
            "/stop_monitor - توقف مانیتورینگ\n"
            "/status - نمایش وضعیت فعلی",
            parse_mode='Markdown'
        )

    async def set_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم ارز برای مانیتورینگ"""
        logger.info(f"دریافت دستور set_coin از کاربر {update.effective_user.id}")
        context.user_data['waiting_for'] = 'coin'
        await update.message.reply_text("لطفاً نماد ارز را وارد کنید (مثلاً BTC یا ETH):")

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم اهرم"""
        logger.info(f"دریافت دستور set_leverage از کاربر {update.effective_user.id}")
        if 'coin' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا ارز را تنظیم کنید (/set_coin)")
            return
        context.user_data['waiting_for'] = 'leverage'
        await update.message.reply_text("لطفاً مقدار اهرم را وارد کنید (مثلاً 2 برای 2x):")

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم درصد سرمایه"""
        logger.info(f"دریافت دستور set_alloc از کاربر {update.effective_user.id}")
        if 'leverage' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا اهرم را تنظیم کنید (/set_leverage)")
            return
        context.user_data['waiting_for'] = 'allocation'
        await update.message.reply_text("لطفاً درصد سرمایه را وارد کنید (مثلاً 50 برای 50%):")

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم درصد تغییر هدف"""
        logger.info(f"دریافت دستور set_target از کاربر {update.effective_user.id}")
        if 'allocation' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً ابتدا درصد سرمایه را تنظیم کنید (/set_alloc)")
            return
        context.user_data['waiting_for'] = 'target'
        await update.message.reply_text("لطفاً درصد تغییر هدف را وارد کنید (مثلاً 5 برای 5%):")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش وضعیت فعلی"""
        logger.info(f"دریافت دستور status از کاربر {update.effective_user.id}")
        user_data = context.user_data
        
        if not user_data:
            await update.message.reply_text("⚠️ هنوز تنظیماتی انجام نشده است")
            return
        
        message = "📊 وضعیت فعلی:\n\n"
        if 'coin' in user_data:
            price = await self.get_kucoin_price(user_data['coin'])
            message += f"🏷️ ارز: {user_data['coin']} (قیمت فعلی: {price if price else 'نامعلوم'}$)\n"
        if 'leverage' in user_data:
            message += f"📈 اهرم: {user_data['leverage']}x\n"
        if 'allocation' in user_data:
            message += f"💰 تخصیص: {user_data['allocation']}%\n"
        if 'target_change' in user_data:
            message += f"🎯 درصد تغییر هدف: {user_data['target_change']}%\n"
        if 'monitoring' in user_data:
            message += f"🔍 وضعیت مانیتورینگ: {'فعال' if user_data['monitoring'] else 'غیرفعال'}\n"
        
        await update.message.reply_text(message)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش پیام‌های متنی"""
        logger.info(f"پیام دریافت شد از {update.effective_user.id}: {update.message.text}")
        
        if 'waiting_for' not in context.user_data:
            await update.message.reply_text("⚠️ لطفاً از دستورات استفاده کنید")
            return

        text = update.message.text.strip().upper()
        waiting_for = context.user_data['waiting_for']

        try:
            if waiting_for == 'coin':
                # بررسی وجود جفت ارز در کوکوین
                symbol = f"{text}-USDT"
                price = await self.get_kucoin_price(symbol)
                if price is None:
                    await update.message.reply_text(f"⚠️ ارز {text} در کوکوین یافت نشد")
                    return
                
                context.user_data['coin'] = symbol
                await update.message.reply_text(f"✅ ارز {text} تنظیم شد (قیمت فعلی: {price:.2f}$)")
                await self.set_leverage(update, context)

            elif waiting_for == 'leverage':
                leverage = float(text)
                if not 1 <= leverage <= 100:
                    raise ValueError("اهرم باید بین 1 تا 100 باشد")
                context.user_data['leverage'] = leverage
                await update.message.reply_text(f"✅ اهرم {leverage}x تنظیم شد")
                await self.set_allocation(update, context)

            elif waiting_for == 'allocation':
                alloc = float(text)
                if not 0 < alloc <= 100:
                    raise ValueError("تخصیص باید بین 0 تا 100 باشد")
                context.user_data['allocation'] = alloc
                await update.message.reply_text(f"✅ تخصیص {alloc}% تنظیم شد")
                await self.set_target(update, context)

            elif waiting_for == 'target':
                target = float(text)
                if target <= 0:
                    raise ValueError("درصد تغییر باید بزرگتر از 0 باشد")
                context.user_data['target_change'] = target
                
                # دریافت قیمت فعلی برای نمایش
                price = await self.get_kucoin_price(context.user_data['coin'])
                await update.message.reply_text(
                    f"✅ تنظیمات کامل شد:\n\n"
                    f"🏷️ ارز: {context.user_data['coin']}\n"
                    f"📊 اهرم: {context.user_data['leverage']}x\n"
                    f"💰 تخصیص: {context.user_data['allocation']}%\n"
                    f"🎯 درصد تغییر هدف: {context.user_data['target_change']}%\n"
                    f"💵 قیمت فعلی: {price:.2f}$\n\n"
                    f"برای شروع مانیتورینگ از /start_monitor استفاده کنید"
                )
                context.user_data.pop('waiting_for', None)

        except ValueError as e:
            await update.message.reply_text(f"⚠️ خطا: {str(e)}")
            return
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در handle_message: {e}")
            await update.message.reply_text("⚠️ خطای داخلی رخ داد. لطفاً دوباره امتحان کنید.")
            return

    async def monitor_task(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """وظیفه مانیتورینگ در پس‌زمینه"""
        logger.info(f"شروع مانیتورینگ برای کاربر {user_id}")
        
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
            except asyncio.CancelledError:
                logger.info(f"مانیتورینگ برای کاربر {user_id} لغو شد")
                break
            except Exception as e:
                logger.error(f"خطا در مانیتورینگ برای کاربر {user_id}: {e}")
                await asyncio.sleep(300)

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع مانیتورینگ"""
        user_id = update.effective_user.id
        logger.info(f"دریافت دستور start_monitor از کاربر {user_id}")
        
        required_keys = ['coin', 'leverage', 'allocation', 'target_change']
        
        if not all(key in context.user_data for key in required_keys):
            missing = [k for k in required_keys if k not in context.user_data]
            await update.message.reply_text(
                f"⚠️ لطفاً ابتدا تنظیمات را کامل کنید. موارد缺失: {', '.join(missing)}"
            )
            return
        
        if context.user_data.get('monitoring'):
            await update.message.reply_text("⚠️ مانیتورینگ در حال اجراست")
            return

        context.user_data['monitoring'] = True
        context.user_data['last_price'] = await self.get_kucoin_price(context.user_data['coin'])
        
        # لغو تسک قبلی اگر وجود دارد
        if user_id in self.monitoring_tasks:
            self.monitoring_tasks[user_id].cancel()
            try:
                await self.monitoring_tasks[user_id]
            except asyncio.CancelledError:
                pass
        
        # ایجاد تسک جدید
        task = asyncio.create_task(self.monitor_task(user_id, context))
        self.monitoring_tasks[user_id] = task
        
        await update.message.reply_text(
            f"🔍 مانیتورینگ {context.user_data['coin']} شروع شد\n"
            f"هر تغییر {context.user_data['target_change']}% با اهرم {context.user_data['leverage']}x اطلاع داده می‌شود"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """توقف مانیتورینگ"""
        user_id = update.effective_user.id
        logger.info(f"دریافت دستور stop_monitor از کاربر {user_id}")
        
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
        CommandHandler("status", bot.status),
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
        # توقف تمام تسک‌های مانیتورینگ
        for task in bot.monitoring_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
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
