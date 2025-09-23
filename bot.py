#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import sqlite3
from datetime import datetime
import os

# تنظیمات
BASE_URL = "https://publicapi.ramzinex.com/exchange/api/v1.0/exchange"
TELEGRAM_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# دیتابیس برای ذخیره تنظیمات کاربران
def init_db():
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    # حذف جدول قدیمی اگر وجود دارد
    c.execute('''DROP TABLE IF EXISTS alerts''')
    
    # ایجاد جدول جدید با ساختار صحیح
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, currency TEXT, threshold REAL, 
                  last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency))''')
    conn.commit()
    conn.close()

def debug_api_response(pair_id):
    """تابع برای دیباگ و بررسی ساختار واقعی پاسخ API"""
    try:
        response = requests.get(f"{BASE_URL}/orderbooks/{pair_id}/trades")
        logger.info(f"Debug API Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Full API response structure: {json.dumps(data, indent=2)}")
            
            # بررسی ساختار پاسخ
            if isinstance(data, dict):
                if 'status' in data:
                    logger.info(f"Status: {data['status']}")
                if 'data' in data:
                    logger.info(f"Data type: {type(data['data'])}")
                    if isinstance(data['data'], list) and len(data['data']) > 0:
                        logger.info(f"First trade item: {data['data'][0]}")
            return data
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Debug error: {e}")
        return None

def get_currency_pair_id(currency_symbol):
    """یافتن pair_id مربوط به یک ارز خاص"""
    # بر اساس مستندات رمزینکس و تست‌های واقعی
    currency_mapping = {
        'BTC': 11,    # بیت‌کوین
        'ETH': 12,    # اتریوم
        'USDT': 21,   # تتر
        'IRT': 1,     # ریال ایران
        'LTC': 13,    # لایت‌کوین
        'XRP': 14,    # ریپل
        'ADA': 15,    # کاردانو
        'DOT': 16,    # پولکادات
        'BCH': 17,    # بیت‌کوین کش
        'LINK': 18,   # چین لینک
        'DOGE': 19,   # دوج‌کوین
        'MATIC': 20,  # پالیگان
    }
    
    return currency_mapping.get(currency_symbol.upper())

def get_price(currency_symbol):
    """دریافت قیمت از رمزینکس با استفاده از API معاملات"""
    try:
        pair_id = get_currency_pair_id(currency_symbol)
        if not pair_id:
            logger.warning(f"No pair_id mapping found for {currency_symbol}")
            return None
        
        # ابتدا ساختار پاسخ را دیباگ می‌کنیم
        debug_data = debug_api_response(pair_id)
        if not debug_data:
            return None
        
        # بررسی ساختار پاسخ بر اساس دیباگ
        if isinstance(debug_data, dict) and debug_data.get('status') == 0:
            trades = debug_data.get('data', [])
            if trades and len(trades) > 0:
                # آخرین معامله را به عنوان قیمت فعلی در نظر می‌گیریم
                last_trade = trades[0]
                
                # استخراج قیمت از آخرین معامله - بررسی فیلدهای مختلف
                price = None
                if 'price' in last_trade:
                    price = last_trade['price']
                elif 'last_price' in last_trade:
                    price = last_trade['last_price']
                elif 'amount' in last_trade:  # ممکن است فیلد amount قیمت باشد
                    price = last_trade['amount']
                elif 'value' in last_trade:   # یا فیلد value
                    price = last_trade['value']
                
                if price:
                    logger.info(f"Found price for {currency_symbol}: {price}")
                    return float(price)
                else:
                    logger.warning(f"No price field found in trade data: {last_trade}")
        
        logger.warning(f"No valid price data found for {currency_symbol}")
        return None
            
    except Exception as e:
        logger.error(f"Error getting price for {currency_symbol}: {e}")
        return None

def get_all_currencies():
    """دریافت لیست تمام ارزهای قابل معامله"""
    currencies = list(get_currency_pair_id.keys())
    return sorted(currencies)

async def start(update: Update, context: CallbackContext):
    """دستور شروع"""
    welcome_text = """
🤖 **ربات اطلاع‌رسانی تغییرات قیمت رمزینکس**

با این ربات می‌توانید برای تغییرات قیمت ارزهای مختلف در صرافی رمزینکس هشدار دریافت کنید.

📋 **دستورات موجود:**
/set [ارز] [درصد] - تنظیم هشدار (مثال: `/set btc 5`)
/list - نمایش هشدارهای فعال
/remove [ارز] - حذف هشدار (مثال: `/remove btc`)
/currencies - لیست ارزهای قابل دسترسی
/test [ارز] - تست دریافت قیمت یک ارز (مثال: `/test btc`)
/debug [ارز] - دیباگ و بررسی ساختار API (مثال: `/debug btc`)

💡 **مثال:**
`/set btc 5` - هشدار برای تغییر ۵٪ بیت‌کوین
`/set eth 10` - هشدار برای تغییر ۱۰٪ اتریوم

🔗 **پشتیبانی از صرافی رمزینکس**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def debug_api(update: Update, context: CallbackContext):
    """دیباگ و بررسی ساختار API"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/debug btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    pair_id = get_currency_pair_id(currency)
    
    if not pair_id:
        await update.message.reply_text(f"❌ pair_id برای ارز {currency} یافت نشد.")
        return
    
    await update.message.reply_text(f"🔧 در حال دیباگ API برای {currency} (pair_id: {pair_id})...")
    
    debug_data = debug_api_response(pair_id)
    
    if debug_data:
        # نمایش خلاصه‌ای از ساختار پاسخ
        summary = f"✅ پاسخ API برای {currency}:\n\n"
        summary += f"• Status: {debug_data.get('status', 'N/A')}\n"
        
        if 'data' in debug_data:
            data = debug_data['data']
            summary += f"• Data type: {type(data)}\n"
            if isinstance(data, list):
                summary += f"• Number of trades: {len(data)}\n"
                if len(data) > 0:
                    summary += f"• First trade keys: {list(data[0].keys())}\n"
                    summary += f"• First trade values: {data[0]}\n"
        
        await update.message.reply_text(summary)
    else:
        await update.message.reply_text("❌ خطا در دریافت داده از API")

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/test btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    await update.message.reply_text(f"🔍 در حال دریافت قیمت {currency}...")
    
    price = get_price(currency)
    
    if price is not None:
        await update.message.reply_text(f"✅ قیمت {currency}: {price:,.0f} تومان")
    else:
        currencies = get_all_currencies()
        if currencies:
            await update.message.reply_text(
                f"❌ ارز {currency} یافت نشد.\n\n"
                f"✅ ارزهای موجود: {', '.join(currencies)}"
            )
        else:
            await update.message.reply_text("❌ خطا در اتصال به API رمزینکس")

async def set_alert(update: Update, context: CallbackContext):
    """تنظیم هشدار جدید"""
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) != 2:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/set btc 5`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    try:
        threshold = float(args[1])
        if threshold <= 0:
            await update.message.reply_text("❌ درصد باید بزرگتر از صفر باشد.")
            return
    except ValueError:
        await update.message.reply_text("❌ درصد باید یک عدد باشد.")
        return
    
    # بررسی وجود ارز
    pair_id = get_currency_pair_id(currency)
    if not pair_id:
        currencies_list = get_all_currencies()
        if currencies_list:
            await update.message.reply_text(
                f"❌ ارز {currency} یافت نشد.\n\n"
                f"✅ ارزهای موجود: {', '.join(currencies_list)}\n"
            )
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور")
        return
    
    current_price = get_price(currency)
    if current_price is None:
        await update.message.reply_text("❌ خطا در دریافت قیمت فعلی از سرور رمزینکس")
        return
    
    # ذخیره در دیتابیس
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT OR REPLACE INTO alerts 
                     (user_id, currency, threshold, last_price) 
                     VALUES (?, ?, ?, ?)''', 
                 (user_id, currency, threshold, current_price))
        conn.commit()
        
        await update.message.reply_text(
            f"✅ هشدار تنظیم شد!\n"
            f"• ارز: {currency}\n"
            f"• درصد تغییر: {threshold}%\n"
            f"• قیمت فعلی: {current_price:,.0f} تومان\n\n"
            f"از این لحظه، هرگاه قیمت {threshold}% تغییر کند به شما اطلاع می‌دهم."
        )
    except Exception as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("❌ خطا در ذخیره‌سازی داده‌ها")
    finally:
        conn.close()

async def list_alerts(update: Update, context: CallbackContext):
    """نمایش هشدارهای فعال"""
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('SELECT currency, threshold, last_price FROM alerts WHERE user_id = ?', (user_id,))
    alerts = c.fetchall()
    conn.close()
    
    if not alerts:
        await update.message.reply_text("📭 هیچ هشدار فعالی ندارید.")
        return
    
    text = "🔔 **هشدارهای فعال شما:**\n\n"
    for currency, threshold, last_price in alerts:
        current_price = get_price(currency)
        if current_price:
            change = ((current_price - last_price) / last_price) * 100
            text += f"• {currency}: {threshold}% (تغییر فعلی: {change:+.1f}%)\n"
        else:
            text += f"• {currency}: {threshold}% (خطا در دریافت قیمت)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def remove_alert(update: Update, context: CallbackContext):
    """حذف هشدار"""
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/remove btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('DELETE FROM alerts WHERE user_id = ? AND currency = ?', (user_id, currency))
    conn.commit()
    
    if c.rowcount > 0:
        await update.message.reply_text(f"✅ هشدار برای ارز {currency} حذف شد.")
    else:
        await update.message.reply_text(f"❌ هشداری برای ارز {currency} پیدا نشد.")
    
    conn.close()

async def list_currencies(update: Update, context: CallbackContext):
    """لیست ارزهای قابل دسترسی"""
    try:
        currencies = get_all_currencies()
        
        if currencies:
            text = f"💰 **ارزهای قابل دسترسی ({len(currencies)} ارز):**\n\n"
            text += ", ".join(currencies)
            
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور رمزینکس")
            
    except Exception as e:
        logger.error(f"Error in list_currencies: {e}")
        await update.message.reply_text("❌ خطا در ارتباط با سرور رمزینکس")

async def check_alerts(context: CallbackContext):
    """بررسی هشدارها هر 30 ثانیه"""
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('SELECT user_id, currency, threshold, last_price FROM alerts')
    alerts = c.fetchall()
    
    for user_id, currency, threshold, last_price in alerts:
        current_price = get_price(currency)
        if current_price and last_price:
            change_percent = ((current_price - last_price) / last_price) * 100
            
            # بررسی آیا تغییر از آستانه گذشته است
            if abs(change_percent) >= threshold:
                try:
                    # ارسال پیام
                    if change_percent > 0:
                        emoji = "📈"
                    else:
                        emoji = "📉"
                    
                    message = (
                        f"{emoji} **هشدار قیمت رمزینکس!**\n\n"
                        f"• ارز: {currency}\n"
                        f"• تغییر: {change_percent:+.1f}%\n"
                        f"• قیمت قبلی: {last_price:,.0f} تومان\n"
                        f"• قیمت فعلی: {current_price:,.0f} تومان\n"
                        f"• آستانه: {threshold}%\n"
                        f"• زمان: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    
                    await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                    
                    # آپدیت قیمت آخر
                    c.execute('UPDATE alerts SET last_price = ? WHERE user_id = ? AND currency = ?',
                             (current_price, user_id, currency))
                    
                    logger.info(f"Alert sent to {user_id} for {currency}: {change_percent:.1f}%")
                    
                except Exception as e:
                    logger.error(f"Error sending alert to {user_id}: {e}")
    
    conn.commit()
    conn.close()

def main():
    """تابع اصلی"""
    # مقداردهی اولیه دیتابیس
    init_db()
    
    try:
        # ایجاد اپلیکیشن تلگرام
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # اضافه کردن هندلرها
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("set", set_alert))
        application.add_handler(CommandHandler("list", list_alerts))
        application.add_handler(CommandHandler("remove", remove_alert))
        application.add_handler(CommandHandler("currencies", list_currencies))
        application.add_handler(CommandHandler("test", test_price))
        application.add_handler(CommandHandler("debug", debug_api))
        
        # تنظیم چک دوره‌ای هشدارها (هر 30 ثانیه)
        job_queue = application.job_queue
        job_queue.run_repeating(check_alerts, interval=30, first=10)
        
        # شروع ربات
        application.run_polling()
        logger.info("Bot started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
