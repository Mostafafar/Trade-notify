#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import sqlite3
from datetime import datetime

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
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, currency TEXT, threshold REAL, 
                  last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency))''')
    conn.commit()
    conn.close()

def get_all_markets():
    """دریافت لیست تمام بازارهای موجود از رمزینکس"""
    try:
        response = requests.get(f"{BASE_URL}/markets")
        logger.info(f"Markets API Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'data' in data:
                return data['data']
            else:
                logger.error(f"Unexpected markets data structure: {type(data)}")
                return []
        else:
            logger.error(f"Markets API Error: {response.status_code} - {response.text[:200]}")
            return []
            
    except Exception as e:
        logger.error(f"Error getting markets: {e}")
        return []

def get_price(currency_symbol):
    """دریافت قیمت از رمزینکس با API عمومی"""
    try:
        markets = get_all_markets()
        if not markets:
            logger.error("No markets data available")
            return None
        
        # جستجوی بازار مورد نظر
        currency_symbol = currency_symbol.upper()
        for market in markets:
            # بررسی انواع مختلف ساختار بازار
            base_currency = None
            
            if 'base_currency_symbol' in market:
                base_currency = market['base_currency_symbol'].upper()
            elif 'currency1' in market and isinstance(market['currency1'], dict):
                base_currency = market['currency1'].get('symbol', '').upper()
            elif 'symbol' in market:
                # اگر symbol به صورت جفت ارز باشد (مثلاً BTC/IRT)
                symbol_parts = market['symbol'].split('/')
                if len(symbol_parts) > 0:
                    base_currency = symbol_parts[0].upper()
            
            if base_currency == currency_symbol:
                # استخراج قیمت از فیلدهای مختلف
                price = None
                if 'price' in market:
                    price = market['price']
                elif 'last_price' in market:
                    price = market['last_price']
                elif 'lastPrice' in market:
                    price = market['lastPrice']
                elif 'latest' in market:
                    price = market['latest']
                
                if price:
                    logger.info(f"Found {currency_symbol}: {price}")
                    return float(price)
        
        logger.warning(f"Currency {currency_symbol} not found in markets")
        return None
            
    except Exception as e:
        logger.error(f"Error getting price for {currency_symbol}: {e}")
        return None

def get_all_currencies():
    """دریافت لیست تمام ارزهای قابل معامله"""
    try:
        markets = get_all_markets()
        currencies = set()
        
        for market in markets:
            # استخراج نماد ارز پایه
            base_currency = None
            
            if 'base_currency_symbol' in market:
                base_currency = market['base_currency_symbol'].upper()
            elif 'currency1' in market and isinstance(market['currency1'], dict):
                base_currency = market['currency1'].get('symbol', '').upper()
            elif 'symbol' in market:
                symbol_parts = market['symbol'].split('/')
                if len(symbol_parts) > 0:
                    base_currency = symbol_parts[0].upper()
            
            if base_currency:
                currencies.add(base_currency)
        
        return sorted(list(currencies))
        
    except Exception as e:
        logger.error(f"Error getting currencies: {e}")
        return []

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

💡 **مثال:**
`/set btc 5` - هشدار برای تغییر ۵٪ بیت‌کوین
`/set eth 10` - هشدار برای تغییر ۱۰٪ اتریوم

🔗 **پشتیبانی از صرافی رمزینکس**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

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
                f"✅ ارزهای موجود: {', '.join(currencies[:15])}"
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
    current_price = get_price(currency)
    if current_price is None:
        currencies_list = get_all_currencies()
        if currencies_list:
            await update.message.reply_text(
                f"❌ ارز {currency} یافت نشد.\n\n"
                f"✅ ارزهای موجود: {', '.join(currencies_list[:10])}\n"
                f"برای دیدن لیست کامل از /currencies استفاده کنید."
            )
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور")
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
            # نمایش 20 ارز اول
            text += ", ".join(currencies[:20])
            
            if len(currencies) > 20:
                text += f"\n\n... و {len(currencies) - 20} ارز دیگر"
            
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
