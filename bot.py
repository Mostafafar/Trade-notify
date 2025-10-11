import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
import requests
from datetime import datetime
import json

# تنظیمات اولیه
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات تلگرام
BOT_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# 🔑 آیدی عددی ادمین (باید با آیدی تلگرام خودتان جایگزین کنید)
# برای گرفتن آیدی: @userinfobot را در تلگرام استارت کنید
ADMIN_ID = 6680287530  # 🔴 اینجا را با آیدی عددی خودتان تغییر دهید

# دیکشنری برای ذخیره تنظیمات کاربران
user_settings = {}
# دیکشنری برای ذخیره آخرین قیمت‌ها
last_prices = {}
# دیکشنری برای ذخیره اطلاعات کاربران
users_info = {}
# حالت ارسال پیام گروهی برای ادمین
admin_broadcast_mode = {}

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
                'precision': 'full'
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
            for coin in data.get('coins', [])[:5]:
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

coin_monitor = CoinMonitor()

def save_user_data():
    """ذخیره داده‌های کاربر در فایل"""
    try:
        data = {
            'user_settings': user_settings,
            'last_prices': last_prices,
            'users_info': users_info
        }
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

def load_user_data():
    """بارگذاری داده‌های کاربر از فایل"""
    global user_settings, last_prices, users_info
    try:
        if os.path.exists('user_data.json'):
            with open('user_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_settings = data.get('user_settings', {})
                last_prices = data.get('last_prices', {})
                users_info = data.get('users_info', {})
                
                # تبدیل کلیدها به int
                user_settings = {int(k): v for k, v in user_settings.items()}
                users_info = {int(k): v for k, v in users_info.items()}
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

def get_main_keyboard():
    """صفحه کلید اصلی برای کاربران"""
    keyboard = [
        [InlineKeyboardButton("🔍 جستجوی ارز", callback_data="menu_search")],
        [InlineKeyboardButton("📊 لیست مانیتورینگ", callback_data="menu_list")],
        [InlineKeyboardButton("📖 راهنما", callback_data="menu_help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    """صفحه کلید ویژه ادمین"""
    keyboard = [
        [InlineKeyboardButton("👥 آمار کاربران", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔍 جستجوی ارز", callback_data="menu_search")],
        [InlineKeyboardButton("📊 لیست مانیتورینگ", callback_data="menu_list")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def notify_admin_new_user(context: CallbackContext, user):
    """اطلاع‌رسانی به ادمین درباره کاربر جدید"""
    try:
        message = (
            f"👤 **کاربر جدید وارد بات شد!**\n\n"
            f"🔸 نام: {user.first_name} {user.last_name or ''}\n"
            f"🔸 یوزرنیم: @{user.username or 'ندارد'}\n"
            f"🔸 آیدی: `{user.id}`\n"
            f"🔸 زبان: {user.language_code or 'نامشخص'}\n"
            f"🔸 تاریخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=message)
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

async def start(update: Update, context: CallbackContext) -> None:
    """دستور شروع"""
    user = update.effective_user
    user_id = user.id
    
    # ذخیره اطلاعات کاربر
    is_new_user = str(user_id) not in users_info
    
    users_info[user_id] = {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'language_code': user.language_code,
        'first_seen': users_info.get(user_id, {}).get('first_seen', datetime.now().isoformat()),
        'last_seen': datetime.now().isoformat()
    }
    save_user_data()
    
    # اطلاع به ادمین در صورت کاربر جدید بودن
    if is_new_user:
        await notify_admin_new_user(context, user)
    
    welcome_text = f"""
👋 سلام {user.first_name} عزیز!

🤖 **به ربات مانیتورینگ قیمت ارزهای دیجیتال خوش آمدید**

این ربات به شما کمک می‌کند تا تغییرات قیمت ارزهای دیجیتال را به صورت لحظه‌ای رصد کنید.

🔹 **امکانات:**
✅ جستجوی آسان ارزهای دیجیتال
✅ تنظیم هشدار تغییر قیمت
✅ نمایش قیمت با دقت بالا (۶ رقم اعشار)
✅ اعلان خودکار تغییرات

از منوی زیر انتخاب کنید 👇
    """
    
    # نمایش منوی متناسب با نقش کاربر
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            welcome_text + "\n\n⭐ **شما ادمین ربات هستید**",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(welcome_text, reply_markup=get_main_keyboard())

async def button_callback(update: Update, context: CallbackContext) -> None:
    """مدیریت دکمه‌های منو"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "menu_search":
        text = (
            "🔍 **جستجوی ارز**\n\n"
            "برای جستجو، از دستور زیر استفاده کنید:\n"
            "`/search نام_ارز`\n\n"
            "**مثال:**\n"
            "`/search bitcoin`\n"
            "`/search ethereum`"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")
        ]]))
    
    elif data == "menu_list":
        if user_id not in user_settings or not user_settings[user_id]:
            text = "❌ هیچ ارزی برای مانیتورینگ تنظیم نشده است.\n\nابتدا با /search ارز مورد نظر را پیدا کنید."
        else:
            text = "📊 **ارزهای تحت مانیتورینگ:**\n\n"
            for coin_id, settings in user_settings[user_id].items():
                current_price = last_prices.get(coin_id, 'نامعلوم')
                text += f"🔸 **{coin_id.upper()}**\n"
                text += f"   درصد: {format_percent(settings['percent'])}\n"
                text += f"   قیمت: {format_price(current_price)}\n\n"
            
            text += "\n💡 برای حذف: `/remove نام_ارز`"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")
        ]]))
    
    elif data == "menu_help":
        help_text = """
📖 **راهنمای استفاده**

🔹 **جستجوی ارز:**
`/search bitcoin`

🔹 **تنظیم مانیتورینگ:**
`/set bitcoin 0.5`
(هشدار در تغییر 0.5 درصدی)

🔹 **مشاهده لیست:**
`/list`

🔹 **حذف ارز:**
`/remove bitcoin`

📌 **نکات مهم:**
• درصد حداقل 0.001٪ باشد
• ربات هر 60 ثانیه چک می‌کند
• قیمت‌ها با دقت بالا نمایش داده می‌شوند
        """
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")
        ]]))
    
    elif data == "menu_back":
        if user_id == ADMIN_ID:
            text = "⭐ **پنل ادمین**\nیکی از گزینه‌ها را انتخاب کنید:"
            await query.edit_message_text(text, reply_markup=get_admin_keyboard())
        else:
            text = "🏠 **منوی اصلی**\nیکی از گزینه‌ها را انتخاب کنید:"
            await query.edit_message_text(text, reply_markup=get_main_keyboard())
    
    elif data == "admin_stats" and user_id == ADMIN_ID:
        total_users = len(users_info)
        active_monitors = sum(1 for u in user_settings.values() if u)
        total_coins = len(set(coin for u in user_settings.values() for coin in u.keys()))
        
        text = f"""
📊 **آمار ربات**

👥 تعداد کل کاربران: {total_users}
📈 کاربران با مانیتور فعال: {active_monitors}
💰 تعداد ارزهای منحصربفرد: {total_coins}

**آخرین کاربران:**
        """
        
        sorted_users = sorted(users_info.items(), key=lambda x: x[1]['last_seen'], reverse=True)[:5]
        for uid, info in sorted_users:
            text += f"\n• {info['first_name']} (@{info.get('username', 'بدون یوزرنیم')})"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")
        ]]))
    
    elif data == "admin_broadcast" and user_id == ADMIN_ID:
        admin_broadcast_mode[user_id] = True
        text = """
📢 **ارسال پیام همگانی**

پیام خود را تایپ کرده و ارسال کنید.
پیام به تمام کاربران ربات ارسال خواهد شد.

❌ برای لغو: /cancel
        """
        await query.edit_message_text(text)

async def handle_broadcast(update: Update, context: CallbackContext) -> None:
    """مدیریت پیام‌های ادمین برای ارسال همگانی"""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID and admin_broadcast_mode.get(user_id, False):
        message_text = update.message.text
        
        if message_text == "/cancel":
            admin_broadcast_mode[user_id] = False
            await update.message.reply_text("❌ ارسال همگانی لغو شد.", reply_markup=get_admin_keyboard())
            return
        
        # ارسال پیام به همه کاربران
        success_count = 0
        fail_count = 0
        
        await update.message.reply_text("📤 در حال ارسال پیام...")
        
        broadcast_message = f"📢 **پیام از ادمین:**\n\n{message_text}"
        
        for uid in users_info.keys():
            try:
                await context.bot.send_message(chat_id=uid, text=broadcast_message)
                success_count += 1
                await asyncio.sleep(0.05)  # جلوگیری از محدودیت تلگرام
            except Exception as e:
                fail_count += 1
                logger.error(f"Error sending to {uid}: {e}")
        
        admin_broadcast_mode[user_id] = False
        
        result_text = f"""
✅ **ارسال پیام کامل شد**

📊 موفق: {success_count}
❌ ناموفق: {fail_count}
        """
        await update.message.reply_text(result_text, reply_markup=get_admin_keyboard())

async def search_coin(update: Update, context: CallbackContext) -> None:
    """جستجوی ارز"""
    if not context.args:
        await update.message.reply_text(
            "❌ لطفاً نام ارز را وارد کنید.\n\n**مثال:**\n`/search bitcoin`",
            reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard()
        )
        return
    
    query = ' '.join(context.args)
    
    msg = await update.message.reply_text("🔍 در حال جستجو...")
    
    coins = coin_monitor.search_coin(query)
    
    if not coins:
        await msg.edit_text("❌ ارزی یافت نشد.", 
                           reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard())
        return
    
    response = "📋 **نتایج جستجو:**\n\n"
    for i, coin in enumerate(coins, 1):
        response += f"{i}. **{coin['name']}** ({coin['symbol'].upper()})\n"
        response += f"   ID: `{coin['id']}`\n"
        response += f"   رتبه: {coin['market_cap_rank']}\n\n"
    
    response += "🔹 **تنظیم مانیتورینگ:**\n`/set نام_ارز درصد`\n\n**مثال:**\n`/set bitcoin 0.5`"
    await msg.edit_text(response, 
                       reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard())

async def set_monitor(update: Update, context: CallbackContext) -> None:
    """تنظیم مانیتورینگ برای یک ارز"""
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ فرمت نادرست!\n\n**فرمت صحیح:**\n`/set bitcoin 0.5`",
            reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard()
        )
        return
    
    coin_id = context.args[0].lower()
    try:
        percent = float(context.args[1])
        if percent <= 0:
            await update.message.reply_text("❌ درصد باید بزرگتر از صفر باشد.")
            return
        if percent < 0.001:
            await update.message.reply_text("❌ درصد تغییر بسیار کوچک است. حداقل 0.001% مجاز است.")
            return
    except ValueError:
        await update.message.reply_text("❌ درصد باید یک عدد باشد.")
        return
    
    user_id = update.effective_user.id
    
    msg = await update.message.reply_text("⏳ در حال تنظیم...")
    
    price_data = coin_monitor.get_coin_price(coin_id)
    if not price_data:
        await msg.edit_text("❌ ارز یافت نشد. لطفاً ابتدا با /search جستجو کنید.")
        return
    
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    user_settings[user_id][coin_id] = {
        'percent': percent,
        'last_price': price_data['price'],
        'timestamp': datetime.now().isoformat()
    }
    
    last_prices[coin_id] = price_data['price']
    save_user_data()
    
    await msg.edit_text(
        f"✅ **مانیتورینگ فعال شد!**\n\n"
        f"🔸 ارز: {coin_id.upper()}\n"
        f"🔸 درصد: {format_percent(percent)}\n"
        f"🔸 قیمت: {format_price(price_data['price'])}\n\n"
        f"🔔 هشدار در تغییر ±{format_percent(percent)}",
        reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
    )

async def list_monitors(update: Update, context: CallbackContext) -> None:
    """نمایش لیست ارزهای تحت مانیتورینگ"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings or not user_settings[user_id]:
        await update.message.reply_text(
            "❌ هیچ ارزی تنظیم نشده است.\n\n💡 با /search شروع کنید!",
            reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
        )
        return
    
    response = "📊 **ارزهای تحت مانیتورینگ:**\n\n"
    for coin_id, settings in user_settings[user_id].items():
        current_price = last_prices.get(coin_id, 'نامعلوم')
        response += f"🔸 **{coin_id.upper()}**\n"
        response += f"   درصد: {format_percent(settings['percent'])}\n"
        response += f"   قیمت: {format_price(current_price)}\n\n"
    
    response += "💡 **حذف ارز:**\n`/remove نام_ارز`"
    await update.message.reply_text(response, 
                                   reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard())

async def remove_monitor(update: Update, context: CallbackContext) -> None:
    """حذف ارز از لیست مانیتورینگ"""
    if not context.args:
        await update.message.reply_text("❌ فرمت: `/remove bitcoin`")
        return
    
    coin_id = context.args[0].lower()
    user_id = update.effective_user.id
    
    if user_id in user_settings and coin_id in user_settings[user_id]:
        del user_settings[user_id][coin_id]
        if not any(coin_id in settings for settings in user_settings.values()):
            last_prices.pop(coin_id, None)
        
        save_user_data()
        await update.message.reply_text(
            f"✅ ارز **{coin_id.upper()}** حذف شد.",
            reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
        )
    else:
        await update.message.reply_text("❌ این ارز در لیست شما نیست.")

async def help_command(update: Update, context: CallbackContext) -> None:
    """دستور راهنما"""
    help_text = """
📖 **راهنمای کامل**

🔹 **جستجو:**
`/search bitcoin`

🔹 **تنظیم مانیتور:**
`/set bitcoin 0.5`

🔹 **لیست:**
`/list`

🔹 **حذف:**
`/remove bitcoin`

📌 **نکات:**
• حداقل درصد: 0.001%
• بررسی هر 60 ثانیه
• دقت 6 رقم اعشار
    """
    await update.message.reply_text(help_text, 
                                   reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard())

async def admin_command(update: Update, context: CallbackContext) -> None:
    """دستور ادمین"""
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        await update.message.reply_text("⭐ **پنل ادمین**", reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")

async def price_checker(context: CallbackContext) -> None:
    """بررسی دوره‌ای قیمت‌ها و ارسال اعلان"""
    if not user_settings:
        return
    
    try:
        coins_to_check = set()
        for user_id, coins in user_settings.items():
            coins_to_check.update(coins.keys())
        
        if not coins_to_check:
            return
        
        for coin_id in coins_to_check:
            price_data = coin_monitor.get_coin_price(coin_id)
            if not price_data:
                continue
            
            new_price = price_data['price']
            
            for user_id, coins in user_settings.items():
                if coin_id in coins:
                    settings = coins[coin_id]
                    percent_threshold = settings['percent']
                    user_last_price = settings['last_price']
                    
                    price_change = ((new_price - user_last_price) / user_last_price) * 100
                    
                    if abs(price_change) >= percent_threshold:
                        direction = "📈 صعود" if price_change > 0 else "📉 نزول"
                        message = (
                            f"🚨 **هشدار تغییر قیمت!**\n\n"
                            f"🔸 ارز: {coin_id.upper()}\n"
                            f"🔸 جهت: {direction}\n"
                            f"🔸 تغییر: {price_change:+.4f}%\n"
                            f"🔸 قبلی: {format_price(user_last_price)}\n"
                            f"🔸 جدید: {format_price(new_price)}\n"
                            f"🔸 آستانه: {format_percent(percent_threshold)}"
                        )
                        
                        try:
                            await context.bot.send_message(chat_id=user_id, text=message)
                            user_settings[user_id][coin_id]['last_price'] = new_price
                            save_user_data()
                        except Exception as e:
                            logger.error(f"Error sending notification to {user_id}: {e}")
            
            last_prices[coin_id] = new_price
        
    except Exception as e:
        logger.error(f"Error in price checker: {e}")

def main() -> None:
    """تابع اصلی"""
    load_user_data()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_coin))
    application.add_handler(CommandHandler("set", set_monitor))
    application.add_handler(CommandHandler("list", list_monitors))
    application.add_handler(CommandHandler("remove", remove_monitor))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # کالبک‌های منو
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # مدیریت پیام‌های متنی (برای broadcast)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    
    # Job برای چک کردن قیمت‌ها
    job_queue = application.job_queue
    job_queue.run_repeating(price_checker, interval=60, first=10)
    
    logger.info("🚀 Bot started successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()
