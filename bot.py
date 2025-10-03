import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters
import requests
from datetime import datetime
import json

# تنظیمات اولیه
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات تلگرام - باید از BotFather بگیرید
BOT_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# دیکشنری برای ذخیره تنظیمات کاربران
user_settings = {}
# دیکشنری برای ذخیره آخرین قیمت‌ها
last_prices = {}

class CoinMonitor:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
    
    def get_coin_price(self, coin_id):
        """دریافت قیمت فعلی ارز از CoinGecko"""
        try:
            url = f"{self.base_url}/simple/price"
            params = {
                'ids': coin_id,
                'vs_currencies': 'usd',
                'include_24hr_change': 'true',
                'precision': 'full'  # افزایش دقت
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if coin_id in data:
                return {
                    'price': data[coin_id]['usd'],
                    'change_24h': data[coin_id].get('usd_24h_change', 0)
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching price for {coin_id}: {e}")
            return None
    
    def search_coin(self, query):
        """جستجوی ارز بر اساس نام یا نماد"""
        try:
            url = f"{self.base_url}/search"
            params = {'query': query}
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            coins = []
            for coin in data.get('coins', [])[:5]:  # فقط 5 نتیجه اول
                coins.append({
                    'id': coin['id'],
                    'name': coin['name'],
                    'symbol': coin['symbol'],
                    'market_cap_rank': coin.get('market_cap_rank', 'N/A')
                })
            return coins
        except Exception as e:
            logger.error(f"Error searching coin {query}: {e}")
            return []

# ایجاد نمونه از مانیتور
coin_monitor = CoinMonitor()

def save_user_data():
    """ذخیره داده‌های کاربر در فایل"""
    try:
        data = {
            'user_settings': user_settings,
            'last_prices': last_prices
        }
        with open('user_data.json', 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

def load_user_data():
    """بارگذاری داده‌های کاربر از فایل"""
    global user_settings, last_prices
    try:
        if os.path.exists('user_data.json'):
            with open('user_data.json', 'r') as f:
                data = json.load(f)
                user_settings = data.get('user_settings', {})
                last_prices = data.get('last_prices', {})
    except Exception as e:
        logger.error(f"Error loading user data: {e}")

def format_price(price):
    """فرمت‌دهی قیمت با ۶ رقم اعشار"""
    if isinstance(price, (int, float)):
        return f"${price:,.6f}"
    return str(price)

def format_percent(percent):
    """فرمت‌دهی درصد با ۴ رقم اعشار"""
    if isinstance(percent, (int, float)):
        return f"{percent:.4f}%"
    return str(percent)

async def start(update: Update, context: CallbackContext) -> None:
    """دستور شروع"""
    user_id = update.effective_user.id
    welcome_text = """
🤖 **ربات مانیتورینگ قیمت ارزهای دیجیتال**

🔸 **دستورات موجود:**
/search [نام ارز] - جستجوی ارز (مثال: /search bitcoin)
/set [id ارز] [درصد] - تنظیم مانیتورینگ (مثال: /set bitcoin 0.5)
/list - نمایش لیست ارزهای تحت مانیتورینگ
/remove [id ارز] - حذف ارز از لیست مانیتورینگ
/help - راهنما

🔸 **مثال:**
1. ابتدا ارز را جستجو کنید:
/search bitcoin

2. سپس مانیتورینگ را تنظیم کنید:
/set bitcoin 0.5

ربات هرگاه قیمت 0.5% تغییر کند به شما اطلاع می‌دهد.

🔸 **دقت:**
- قیمت‌ها با ۶ رقم اعشار نمایش داده می‌شوند
- درصد تغییرات با دقت بالا محاسبه می‌شود
    """
    await update.message.reply_text(welcome_text)

async def search_coin(update: Update, context: CallbackContext) -> None:
    """جستجوی ارز"""
    if not context.args:
        await update.message.reply_text("❌ لطفاً نام ارز را وارد کنید.\nمثال: /search bitcoin")
        return
    
    query = ' '.join(context.args)
    user_id = update.effective_user.id
    
    await update.message.reply_text("🔍 در حال جستجو...")
    
    coins = coin_monitor.search_coin(query)
    
    if not coins:
        await update.message.reply_text("❌ ارزی یافت نشد.")
        return
    
    response = "📋 **نتایج جستجو:**\n\n"
    for i, coin in enumerate(coins, 1):
        response += f"{i}. **{coin['name']}** ({coin['symbol'].upper()})\n"
        response += f"   ID: `{coin['id']}`\n"
        response += f"   رتبه بازار: {coin['market_cap_rank']}\n\n"
    
    response += "🔹 برای تنظیم مانیتورینگ از دستور /set استفاده کنید.\nمثال: /set bitcoin 0.5"
    await update.message.reply_text(response)

async def set_monitor(update: Update, context: CallbackContext) -> None:
    """تنظیم مانیتورینگ برای یک ارز"""
    if len(context.args) != 2:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: /set bitcoin 0.5")
        return
    
    coin_id = context.args[0].lower()
    try:
        percent = float(context.args[1])
        if percent <= 0:
            await update.message.reply_text("❌ درصد باید بزرگتر از صفر باشد.")
            return
        if percent < 0.001:  # حداقل 0.001%
            await update.message.reply_text("❌ درصد تغییر بسیار کوچک است. حداقل 0.001% مجاز است.")
            return
    except ValueError:
        await update.message.reply_text("❌ درصد باید یک عدد باشد.")
        return
    
    user_id = update.effective_user.id
    
    # بررسی وجود ارز
    price_data = coin_monitor.get_coin_price(coin_id)
    if not price_data:
        await update.message.reply_text("❌ ارز یافت نشد. لطفاً از صحیح بودن ID مطمئن شوید.")
        return
    
    # ذخیره تنظیمات کاربر
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    user_settings[user_id][coin_id] = {
        'percent': percent,
        'last_price': price_data['price'],
        'timestamp': datetime.now().isoformat()
    }
    
    last_prices[coin_id] = price_data['price']
    
    save_user_data()
    
    await update.message.reply_text(
        f"✅ **مانیتورینگ تنظیم شد**\n\n"
        f"🔸 ارز: {coin_id.upper()}\n"
        f"🔸 درصد تغییر: {format_percent(percent)}\n"
        f"🔸 قیمت فعلی: {format_price(price_data['price'])}\n\n"
        f"ربات هنگام تغییر قیمت ±{format_percent(percent)} به شما اطلاع می‌دهد."
    )

async def list_monitors(update: Update, context: CallbackContext) -> None:
    """نمایش لیست ارزهای تحت مانیتورینگ"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings or not user_settings[user_id]:
        await update.message.reply_text("❌ هیچ ارزی برای مانیتورینگ تنظیم نشده است.")
        return
    
    response = "📊 **ارزهای تحت مانیتورینگ:**\n\n"
    for coin_id, settings in user_settings[user_id].items():
        current_price = last_prices.get(coin_id, 'نامعلوم')
        
        response += f"🔸 **{coin_id.upper()}**\n"
        response += f"   درصد تغییر: {format_percent(settings['percent'])}\n"
        response += f"   قیمت فعلی: {format_price(current_price)}\n\n"
    
    await update.message.reply_text(response)

async def remove_monitor(update: Update, context: CallbackContext) -> None:
    """حذف ارز از لیست مانیتورینگ"""
    if not context.args:
        await update.message.reply_text("❌ لطفاً ID ارز را وارد کنید.\nمثال: /remove bitcoin")
        return
    
    coin_id = context.args[0].lower()
    user_id = update.effective_user.id
    
    if user_id in user_settings and coin_id in user_settings[user_id]:
        del user_settings[user_id][coin_id]
        # اگر کاربر دیگر این ارز را مانیتور نمی‌کند، از last_prices حذف کنیم
        if not any(coin_id in settings for settings in user_settings.values()):
            last_prices.pop(coin_id, None)
        
        save_user_data()
        await update.message.reply_text(f"✅ ارز {coin_id.upper()} از لیست مانیتورینگ حذف شد.")
    else:
        await update.message.reply_text("❌ این ارز در لیست مانیتورینگ شما وجود ندارد.")

async def help_command(update: Update, context: CallbackContext) -> None:
    """دستور راهنما"""
    help_text = """
📖 **راهنما:**

🔹 **جستجوی ارز:**
/search [نام ارز]
مثال: /search bitcoin

🔹 **تنظیم مانیتورینگ:**
/set [id ارز] [درصد]
مثال: /set bitcoin 0.5

🔹 **مشاهده لیست:**
/list

🔹 **حذف ارز:**
/remove [id ارز]
مثال: /remove bitcoin

🔹 **نکات:**
- درصد تغییر باید عددی مثبت باشد (حداقل 0.001%)
- از ID صحیح ارز استفاده کنید (با /search پیدا کنید)
- ربات هر 60 ثانیه قیمت‌ها را چک می‌کند
- قیمت‌ها با دقت ۶ رقم اعشار نمایش داده می‌شوند
- درصد تغییرات با دقت ۴ رقم اعشار محاسبه می‌شود
    """
    await update.message.reply_text(help_text)

async def price_checker(context: CallbackContext) -> None:
    """بررسی دوره‌ای قیمت‌ها و ارسال اعلان"""
    if not user_settings:
        return
    
    try:
        # دریافت قیمت‌های همه ارزهای مورد نیاز
        coins_to_check = set()
        for user_id, coins in user_settings.items():
            coins_to_check.update(coins.keys())
        
        if not coins_to_check:
            return
        
        # دریافت قیمت‌های جدید
        for coin_id in coins_to_check:
            price_data = coin_monitor.get_coin_price(coin_id)
            if not price_data:
                continue
            
            new_price = price_data['price']
            
            # بررسی برای هر کاربر
            for user_id, coins in user_settings.items():
                if coin_id in coins:
                    settings = coins[coin_id]
                    percent_threshold = settings['percent']
                    old_price = settings['last_price']  # قیمت ذخیره شده برای این کاربر
                    
                    if old_price is None:
                        # اولین بار - فقط ذخیره کن
                        user_settings[user_id][coin_id]['last_price'] = new_price
                        continue
                    
                    # محاسبه درصد تغییر با دقت بالا
                    price_change = ((new_price - old_price) / old_price) * 100
                    
                    # بررسی آیا تغییر به اندازه آستانه رسیده است
                    if abs(price_change) >= percent_threshold:
                        # ارسال اعلان
                        direction = "📈 صعود" if price_change > 0 else "📉 نزول"
                        message = (
                            f"🚨 **تغییر قیمت قابل توجه**\n\n"
                            f"🔸 ارز: {coin_id.upper()}\n"
                            f"🔸 جهت: {direction}\n"
                            f"🔸 تغییر: {price_change:+.4f}%\n"
                            f"🔸 قیمت قبلی: {format_price(old_price)}\n"
                            f"🔸 قیمت جدید: {format_price(new_price)}\n"
                            f"🔸 آستانه: {format_percent(percent_threshold)}"
                        )
                        
                        try:
                            await context.bot.send_message(
                                chat_id=user_id, 
                                text=message
                            )
                            logger.info(f"Notification sent to {user_id} for {coin_id}: {price_change:+.4f}%")
                            
                        except Exception as e:
                            logger.error(f"Error sending notification to {user_id}: {e}")
                    
                    # همیشه قیمت را به‌روز کن (حتی اگر اعلان ارسال نشد)
                    user_settings[user_id][coin_id]['last_price'] = new_price
            
            # به‌روزرسانی قیمت جهانی
            last_prices[coin_id] = new_price
        
        save_user_data()
        
    except Exception as e:
        logger.error(f"Error in price checker: {e}")

def main() -> None:
    """تابع اصلی"""
    # بارگذاری داده‌های ذخیره شده
    load_user_data()
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(BOT_TOKEN).build()
    
    # افزودن handlerها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_coin))
    application.add_handler(CommandHandler("set", set_monitor))
    application.add_handler(CommandHandler("list", list_monitors))
    application.add_handler(CommandHandler("remove", remove_monitor))
    application.add_handler(CommandHandler("help", help_command))
    
    # تنظیم job برای بررسی قیمت هر 60 ثانیه
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=60, first=10)
    
    # شروع ربات
    application.run_polling()
    logger.info("Bot started successfully")

if __name__ == '__main__':
    main()
