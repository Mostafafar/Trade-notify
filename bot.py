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

# 🔑 آیدی عددی ادمین
ADMIN_ID = 6680287530

# دیکشنری برای ذخیره تنظیمات کاربران
# ساختار: {user_id: {coin_id: [{'percent': 0.5, 'direction': 'both', 'last_price': 45000}]}}
user_settings = {}
# دیکشنری برای ذخیره آخرین قیمت‌ها
last_prices = {}
# دیکشنری برای ذخیره اطلاعات کاربران
users_info = {}
# حالت ارسال پیام گروهی برای ادمین
admin_broadcast_mode = {}
# پرچم برای کنترل حلقه قیمت
price_checker_running = False

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
✅ تنظیم هشدار تغییر قیمت (با جهت دلخواه)
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
            direction_emoji = {'up': '📈', 'down': '📉', 'both': '↕️'}
            direction_names = {'up': 'صعودی', 'down': 'نزولی', 'both': 'هر دو'}
            
            for coin_id, alerts in user_settings[user_id].items():
                text += f"🔸 **{coin_id.upper()}**\n"
                for i, alert in enumerate(alerts, 1):
                    current_price = last_prices.get(coin_id, 'نامعلوم')
                    text += (
                        f"   {i}. {direction_emoji[alert['direction']]} "
                        f"درصد: {format_percent(alert['percent'])} "
                        f"| قیمت: {format_price(current_price)} "
                        f"| جهت: {direction_names[alert['direction']]}\n"
                    )
                text += "\n"
            
            text += "💡 **حذف یک هشدار:**\n`/remove coin_id درصد جهت`\n"
            text += "**مثال:** `/remove bitcoin 0.5 up`"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="menu_back")
        ]]))
    
    elif data == "menu_help":
        help_text = """
📖 **راهنمای استفاده**

🔹 **جستجوی ارز:**
`/search bitcoin`

🔹 **تنظیم مانیتورینگ:**
`/set bitcoin 0.5` (هر دو جهت)
`/set bitcoin 0.5 up` (فقط صعودی)
`/set bitcoin 0.5 down` (فقط نزولی)

🔹 **مشاهده لیست:**
`/list`

🔹 **حذف ارز:**
`/remove bitcoin 0.5 up`

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
        total_alerts = sum(len(alerts) for u in user_settings.values() for alerts in u.values())
        
        text = f"""
📊 **آمار ربات**

👥 تعداد کل کاربران: {total_users}
📈 کاربران با مانیتور فعال: {active_monitors}
💰 تعداد ارزهای منحصربفرد: {total_coins}
🔔 تعداد کل هشدارها: {total_alerts}

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
                await asyncio.sleep(0.05)
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
    
    response += "🔹 **تنظیم مانیتورینگ:**\n"
    response += "`/set نام_ارز درصد جهت`\n\n"
    response += "**مثال:**\n"
    response += "`/set bitcoin 0.5` (هر دو جهت)\n"
    response += "`/set bitcoin 0.5 up` (فقط صعودی)\n"
    response += "`/set bitcoin 0.5 down` (فقط نزولی)"
    
    await msg.edit_text(response, 
                       reply_markup=get_main_keyboard() if update.effective_user.id != ADMIN_ID else get_admin_keyboard())

async def set_monitor(update: Update, context: CallbackContext) -> None:
    """تنظیم مانیتورینگ برای یک ارز با انتخاب جهت"""
    if len(context.args) < 2 or len(context.args) > 3:
        await update.message.reply_text(
            "❌ فرمت نادرست!\n\n"
            "**فرمت‌های صحیح:**\n"
            "`/set bitcoin 0.5` (هر دو جهت)\n"
            "`/set bitcoin 0.5 up` (فقط صعودی)\n"
            "`/set bitcoin 0.5 down` (فقط نزولی)\n\n"
            "💡 می‌توانید چندین هشدار با درصدهای مختلف تنظیم کنید.",
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
    
    # تعیین جهت هشدار
    direction = 'both'
    if len(context.args) == 3:
        direction_input = context.args[2].lower()
        if direction_input in ['up', 'down', 'both']:
            direction = direction_input
        else:
            await update.message.reply_text(
                "❌ جهت نامعتبر! از `up`، `down` یا `both` استفاده کنید."
            )
            return
    
    user_id = update.effective_user.id
    
    msg = await update.message.reply_text("⏳ در حال تنظیم...")
    
    # دریافت قیمت فعلی ارز
    price_data = coin_monitor.get_coin_price(coin_id)
    if not price_data:
        await msg.edit_text("❌ ارز یافت نشد. لطفاً ابتدا با /search جستجو کنید.")
        return
    
    current_price = price_data['price']
    
    # مقداردهی اولیه برای کاربر
    if user_id not in user_settings:
        user_settings[user_id] = {}
    
    if coin_id not in user_settings[user_id]:
        user_settings[user_id][coin_id] = []
    
    # بررسی عدم تکراری بودن درصد و جهت
    for setting in user_settings[user_id][coin_id]:
        if abs(setting['percent'] - percent) < 0.0001 and setting['direction'] == direction:
            direction_names = {'up': 'صعودی', 'down': 'نزولی', 'both': 'هر دو جهت'}
            await msg.edit_text(
                f"❌ هشدار با درصد {format_percent(percent)} و جهت {direction_names[direction]} "
                f"قبلاً برای {coin_id.upper()} تنظیم شده است."
            )
            return
    
    # اضافه کردن هشدار جدید
    user_settings[user_id][coin_id].append({
        'percent': percent,
        'direction': direction,
        'last_price': current_price,
        'timestamp': datetime.now().isoformat()
    })
    
    last_prices[coin_id] = current_price
    save_user_data()
    
    # نمایش تعداد هشدارهای فعال برای این ارز
    alert_count = len(user_settings[user_id][coin_id])
    
    direction_names = {
        'up': '📈 فقط صعودی',
        'down': '📉 فقط نزولی',
        'both': '↕️ هر دو جهت'
    }
    
    await msg.edit_text(
        f"✅ **هشدار جدید اضافه شد!**\n\n"
        f"🔸 ارز: {coin_id.upper()}\n"
        f"🔸 درصد: {format_percent(percent)}\n"
        f"🔸 جهت: {direction_names[direction]}\n"
        f"🔸 قیمت فعلی: {format_price(current_price)}\n"
        f"🔸 تعداد هشدارهای فعال برای {coin_id.upper()}: {alert_count}\n\n"
        f"🔔 هشدار در تغییر {format_percent(percent)} ({direction_names[direction]})",
        reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
    )

async def list_monitors(update: Update, context: CallbackContext) -> None:
    """نمایش لیست ارزهای تحت مانیتورینگ با تمام هشدارها و جهت"""
    user_id = update.effective_user.id
    
    if user_id not in user_settings or not user_settings[user_id]:
        await update.message.reply_text(
            "❌ هیچ ارزی تنظیم نشده است.\n\n💡 با /search شروع کنید!",
            reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
        )
        return
    
    response = "📊 **ارزهای تحت مانیتورینگ:**\n\n"
    
    direction_emoji = {'up': '📈', 'down': '📉', 'both': '↕️'}
    direction_names = {'up': 'صعودی', 'down': 'نزولی', 'both': 'هر دو'}
    
    for coin_id, alerts in user_settings[user_id].items():
        response += f"🔸 **{coin_id.upper()}**\n"
        for i, alert in enumerate(alerts, 1):
            current_price = last_prices.get(coin_id, 'نامعلوم')
            response += (
                f"   {i}. {direction_emoji[alert['direction']]} "
                f"درصد: {format_percent(alert['percent'])} "
                f"| قیمت: {format_price(current_price)} "
                f"| جهت: {direction_names[alert['direction']]}\n"
            )
        response += "\n"
    
    response += "💡 **حذف یک هشدار:**\n`/remove coin_id درصد جهت`\n"
    response += "**مثال:** `/remove bitcoin 0.5 up`\n"
    response += "**یا:** `/remove bitcoin 0.5` (بدون جهت)"
    
    await update.message.reply_text(
        response,
        reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
    )

async def remove_monitor(update: Update, context: CallbackContext) -> None:
    """حذف یک هشدار خاص از لیست مانیتورینگ"""
    if len(context.args) < 2 or len(context.args) > 3:
        await update.message.reply_text(
            "❌ فرمت: `/remove bitcoin 0.5` یا `/remove bitcoin 0.5 up`"
        )
        return
    
    coin_id = context.args[0].lower()
    try:
        percent = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ درصد باید یک عدد باشد.")
        return
    
    # اگر جهت مشخص شده
    direction = None
    if len(context.args) == 3:
        direction_input = context.args[2].lower()
        if direction_input in ['up', 'down', 'both']:
            direction = direction_input
        else:
            await update.message.reply_text("❌ جهت نامعتبر! از `up`، `down` یا `both` استفاده کنید.")
            return
    
    user_id = update.effective_user.id
    
    if user_id not in user_settings or coin_id not in user_settings[user_id]:
        await update.message.reply_text("❌ این ارز در لیست شما نیست.")
        return
    
    # پیدا کردن و حذف هشدار با درصد و جهت مشخص
    alerts = user_settings[user_id][coin_id]
    removed = False
    
    for i, alert in enumerate(alerts):
        percent_match = abs(alert['percent'] - percent) < 0.0001
        direction_match = True if direction is None else alert['direction'] == direction
        
        if percent_match and direction_match:
            del alerts[i]
            removed = True
            break
    
    if not removed:
        direction_text = f" با جهت {direction}" if direction else ""
        await update.message.reply_text(
            f"❌ هشدار با درصد {format_percent(percent)}{direction_text} برای {coin_id.upper()} یافت نشد."
        )
        return
    
    # اگر لیست هشدارها خالی شد، ارز را حذف کن
    if not alerts:
        del user_settings[user_id][coin_id]
    
    save_user_data()
    
    direction_names = {'up': 'صعودی', 'down': 'نزولی', 'both': 'هر دو'}
    
    await update.message.reply_text(
        f"✅ هشدار با درصد {format_percent(percent)} و جهت {direction_names.get(direction, 'هر دو')} برای **{coin_id.upper()}** حذف شد.",
        reply_markup=get_main_keyboard() if user_id != ADMIN_ID else get_admin_keyboard()
    )

async def help_command(update: Update, context: CallbackContext) -> None:
    """دستور راهنما"""
    help_text = """
📖 **راهنمای کامل**

🔹 **جستجو:**
`/search bitcoin`

🔹 **تنظیم مانیتور:**
`/set bitcoin 0.5` (هر دو جهت)
`/set bitcoin 0.5 up` (فقط صعودی)
`/set bitcoin 0.5 down` (فقط نزولی)

🔹 **لیست:**
`/list`

🔹 **حذف:**
`/remove bitcoin 0.5 up`

📌 **نکات:**
• حداقل درصد: 0.001%
• بررسی هر 60 ثانیه
• دقت 6 رقم اعشار
• امکان تنظیم چندین هشدار برای یک ارز
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
    """بررسی دوره‌ای قیمت‌ها و ارسال اعلان با در نظر گرفتن جهت"""
    if not user_settings:
        return
    
    logger.info("🔄 Running price checker...")
    
    try:
        coins_to_check = set()
        for user_id, coins in user_settings.items():
            for coin_id in coins.keys():
                coins_to_check.add(coin_id)
        
        if not coins_to_check:
            return
        
        for coin_id in coins_to_check:
            price_data = coin_monitor.get_coin_price(coin_id)
            if not price_data:
                continue
            
            new_price = price_data['price']
            
            for user_id, coins in user_settings.items():
                if coin_id not in coins:
                    continue
                
                # بررسی همه هشدارهای این ارز برای کاربر
                for alert in coins[coin_id]:
                    percent_threshold = alert['percent']
                    user_last_price = alert['last_price']
                    direction = alert.get('direction', 'both')
                    
                    price_change = ((new_price - user_last_price) / user_last_price) * 100
                    abs_change = abs(price_change)
                    
                    # بررسی شرایط بر اساس جهت
                    should_notify = False
                    
                    if direction == 'both':
                        should_notify = abs_change >= percent_threshold
                    elif direction == 'up':
                        should_notify = price_change >= percent_threshold
                    elif direction == 'down':
                        should_notify = price_change <= -percent_threshold
                    
                    if should_notify:
                        direction_emoji = "📈 صعود" if price_change > 0 else "📉 نزول"
                        direction_names = {
                            'up': 'فقط صعودی',
                            'down': 'فقط نزولی',
                            'both': 'هر دو جهت'
                        }
                        
                        message = (
                            f"🚨 **هشدار تغییر قیمت!**\n\n"
                            f"🔸 ارز: {coin_id.upper()}\n"
                            f"🔸 جهت: {direction_emoji}\n"
                            f"🔸 تغییر: {price_change:+.4f}%\n"
                            f"🔸 قبلی: {format_price(user_last_price)}\n"
                            f"🔸 جدید: {format_price(new_price)}\n"
                            f"🔸 آستانه: {format_percent(percent_threshold)}\n"
                            f"🔸 نوع هشدار: {direction_names[direction]}"
                        )
                        
                        try:
                            await context.bot.send_message(chat_id=user_id, text=message)
                            # به‌روزرسانی قیمت آخر برای این هشدار
                            alert['last_price'] = new_price
                            save_user_data()
                            logger.info(f"✅ Notification sent to user {user_id} for {coin_id}")
                        except Exception as e:
                            logger.error(f"Error sending notification to {user_id}: {e}")
            
            last_prices[coin_id] = new_price
        
    except Exception as e:
        logger.error(f"Error in price checker: {e}")

async def price_checker_loop(context: CallbackContext):
    """حلقه نامحدود برای بررسی قیمت‌ها"""
    global price_checker_running
    price_checker_running = True
    logger.info("🔄 Price checker loop started!")
    
    while price_checker_running:
        try:
            await price_checker(context)
        except Exception as e:
            logger.error(f"Error in price checker loop: {e}")
        await asyncio.sleep(60)  # هر 60 ثانیه یک بار

async def test_check(update: Update, context: CallbackContext) -> None:
    """تست دستی بررسی قیمت‌ها"""
    user_id = update.effective_user.id
    
    # فقط ادمین می‌تونه تست کنه
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین می‌تونه این دستور رو اجرا کنه.")
        return
    
    await update.message.reply_text("🔄 در حال بررسی قیمت‌ها...")
    await price_checker(context)
    await update.message.reply_text("✅ بررسی کامل شد!")

async def cancel_broadcast(update: Update, context: CallbackContext) -> None:
    """لغو ارسال همگانی"""
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and admin_broadcast_mode.get(user_id, False):
        admin_broadcast_mode[user_id] = False
        await update.message.reply_text("❌ ارسال همگانی لغو شد.", reply_markup=get_admin_keyboard())

async def status_command(update: Update, context: CallbackContext) -> None:
    """نمایش وضعیت بات"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ فقط ادمین می‌تونه این دستور رو اجرا کنه.")
        return
    
    total_users = len(users_info)
    total_alerts = sum(len(alerts) for u in user_settings.values() for alerts in u.values())
    
    status_text = f"""
📊 **وضعیت بات**

🔄 قیمت‌ها: {'فعال' if price_checker_running else 'غیرفعال'}
👥 تعداد کاربران: {total_users}
🔔 تعداد هشدارها: {total_alerts}
⏱️ آخرین بروزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    await update.message.reply_text(status_text)

def main() -> None:
    """تابع اصلی"""
    global price_checker_running
    
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
    application.add_handler(CommandHandler("cancel", cancel_broadcast))
    application.add_handler(CommandHandler("test", test_check))
    application.add_handler(CommandHandler("status", status_command))
    
    # کالبک‌های منو
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # مدیریت پیام‌های متنی (برای broadcast)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast))
    
    # شروع حلقه بررسی قیمت‌ها در پس‌زمینه
    loop = asyncio.get_event_loop()
    loop.create_task(price_checker_loop(application))
    price_checker_running = True
    
    logger.info("🚀 Bot started successfully with price checker loop!")
    application.run_polling()

if __name__ == '__main__':
    main()
