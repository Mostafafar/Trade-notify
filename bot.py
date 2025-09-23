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
BASE_URL = "https://publicapi.ramzinex.com/exchange/api/v2.0/exchange"
TELEGRAM_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# دیتابیس
def init_db():
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, currency TEXT, pair_id INTEGER, threshold REAL, 
                  last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency))''')
    conn.commit()
    conn.close()

def get_all_pairs():
    """دریافت اطلاعات تمام جفت‌ارزها از API رمزینکس"""
    try:
        response = requests.get(f"{BASE_URL}/pairs")
        logger.info(f"Pairs API Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 0 and 'data' in data and 'pairs' in data['data']:
                return data['data']['pairs']
            logger.error(f"Unexpected pairs data structure: {data}")
            return []
        logger.error(f"Pairs API Error: {response.status_code} - {response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"Error getting pairs: {e}")
        return []

def get_currency_pair_id(currency_symbol):
    """یافتن pair_id مربوط به یک ارز خاص"""
    try:
        pairs = get_all_pairs()
        currency_symbol = currency_symbol.upper()
        for pair in pairs:
            base_currency = pair.get('base_currency', {}).get('symbol', {}).get('en', '').upper()
            if base_currency == currency_symbol:
                return pair['id']
        logger.warning(f"No pair_id found for {currency_symbol}")
        return None
    except Exception as e:
        logger.error(f"Error finding pair_id for {currency_symbol}: {e}")
        return None

def get_price(currency_symbol):
    """دریافت قیمت از رمزینکس با استفاده از API معاملات"""
    try:
        pair_id = get_currency_pair_id(currency_symbol)
        if not pair_id:
            logger.warning(f"No pair_id found for {currency_symbol}")
            return None
        
        # فرض: endpoint مشابه در v2.0 وجود دارد
        response = requests.get(f"{BASE_URL}/orderbooks/{pair_id}/trades")
        logger.info(f"Price API Status for {currency_symbol} (pair_id: {pair_id}): {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.debug(f"API response for {currency_symbol}: {data}")
            if data.get('status') == 0 and data.get('data'):
                trades = data.get('data', [])
                if trades:
                    last_trade = trades[0]
                    price = last_trade.get('price') or last_trade.get('last_price')
                    if price:
                        logger.info(f"Found price for {currency_symbol}: {price}")
                        return float(price)
                logger.warning(f"No trades found for {currency_symbol}")
            logger.warning(f"No valid price data found for {currency_symbol}")
            return None
        logger.error(f"Price API Error for {currency_symbol}: {response.status_code} - {response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Error getting price for {currency_symbol}: {e}")
        return None

def get_all_currencies():
    """دریافت لیست تمام ارزهای قابل معامله"""
    try:
        pairs = get_all_pairs()
        currencies = set()
        for pair in pairs:
            base_currency = pair.get('base_currency', {}).get('symbol', {}).get('en', '').upper()
            currencies.add(base_currency)
        return sorted(list(currencies))
    except Exception as e:
        logger.error(f"Error getting currencies: {e}")
        return []

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت یک ارز"""
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/test btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    await update.message.reply_text(f"🔍 در حال دریافت قیمت {currency}...")
    
    pair_id = get_currency_pair_id(currency)
    if not pair_id:
        currencies = get_all_currencies()
        if currencies:
            await update.message.reply_text(
                f"❌ ارز {currency} یافت نشد.\n\n"
                f"✅ ارزهای موجود: {', '.join(currencies)}"
            )
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور")
        return
    
    price = get_price(currency)
    if price is not None:
        await update.message.reply_text(f"✅ قیمت {currency}: {price:,.0f} تومان")
    else:
        await update.message.reply_text(f"❌ خطا در دریافت قیمت {currency}. لطفاً دوباره امتحان کنید.")

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
    
    pair_id = get_currency_pair_id(currency)
    if not pair_id:
        currencies_list = get_all_currencies()
        if currencies_list:
            await update.message.reply_text(
                f"❌ ارز {currency} یافت نشد.\n\n"
                f"✅ ارزهای موجود: {', '.join(currencies_list)}"
            )
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور")
        return
    
    current_price = get_price(currency)
    if current_price is None:
        await update.message.reply_text("❌ خطا در دریافت قیمت فعلی از سرور رمزینکس")
        return
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    try:
        c.execute('''INSERT OR REPLACE INTO alerts 
                     (user_id, currency, pair_id, threshold, last_price) 
                     VALUES (?, ?, ?, ?, ?)''', 
                 (user_id, currency, pair_id, threshold, current_price))
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
    c.execute('SELECT user_id, currency, pair_id, threshold, last_price FROM alerts')
    alerts = c.fetchall()
    
    for user_id, currency, pair_id, threshold, last_price in alerts:
        current_price = get_price(currency)
        if current_price and last_price:
            change_percent = ((current_price - last_price) / last_price) * 100
            if abs(change_percent) >= threshold:
                try:
                    emoji = "📈" if change_percent > 0 else "📉"
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
                    c.execute('UPDATE alerts SET last_price = ? WHERE user_id = ? AND currency = ?',
                             (current_price, user_id, currency))
                    logger.info(f"Alert sent to {user_id} for {currency}: {change_percent:.1f}%")
                except Exception as e:
                    logger.error(f"Error sending alert to {user_id}: {e}")
    
    conn.commit()
    conn.close()

def main():
    init_db()
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("set", set_alert))
        application.add_handler(CommandHandler("list", list_alerts))
        application.add_handler(CommandHandler("remove", remove_alert))
        application.add_handler(CommandHandler("currencies", list_currencies))
        application.add_handler(CommandHandler("test", test_price))
        job_queue = application.job_queue
        job_queue.run_repeating(check_alerts, interval=30, first=10)
        application.run_polling()
        logger.info("Bot started successfully")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
