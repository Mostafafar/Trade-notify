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
BASE_URL = "https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks"
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

def get_pair_id(currency_symbol):
    """دریافت pair_id برای ارز موردنظر"""
    try:
        response = requests.get(f"{BASE_URL}/buys_sells")
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 0:
            for pair_id, market_data in data.get('data', {}).items():
                # فرض: نام جفت‌ارز در پاسخ API مشخص است (مثلاً BTC/USDT)
                # باید با مستندات دقیق‌تر تطبیق داده شود
                if currency_symbol.upper() in pair_id.upper():
                    return pair_id
        logger.warning(f"No pair_id found for {currency_symbol}")
        return None
    except Exception as e:
        logger.error(f"Error getting pair_id for {currency_symbol}: {e}")
        return None

def get_price(currency_symbol):
    """دریافت قیمت آخرین معامله برای ارز"""
    pair_id = get_pair_id(currency_symbol)
    if not pair_id:
        return None
    try:
        response = requests.get(f"{BASE_URL}/{pair_id}/trades")
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 0 and data.get('data'):
            # فرض: اولین معامله در لیست، آخرین قیمت را دارد
            last_trade = data['data'][0]
            price = float(last_trade.get('price')) if 'price' in last_trade else None
            if price:
                logger.info(f"Found {currency_symbol} (pair_id: {pair_id}): {price}")
                return price
        logger.warning(f"No price found for {currency_symbol} (pair_id: {pair_id})")
        return None
    except Exception as e:
        logger.error(f"Error getting price for {currency_symbol}: {e}")
        return None

def get_all_currencies():
    """دریافت لیست تمام جفت‌ارزها"""
    try:
        response = requests.get(f"{BASE_URL}/buys_sells")
        response.raise_for_status()
        data = response.json()
        currencies = set()
        if data.get('status') == 0:
            for pair_id in data.get('data', {}).keys():
                # فرض: pair_id شامل نماد ارز است (مثلاً BTC_USDT)
                currencies.add(pair_id.split('_')[0].upper())
            return sorted(list(currencies))
        logger.error("No currencies found in API response")
        return []
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
    
    pair_id = get_pair_id(currency)
    if not pair_id:
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
    
    current_price = get_price(currency)
    if current_price is None:
        await update.message.reply_text("❌ خطا در دریافت قیمت فعلی")
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

# سایر توابع (start, list_alerts, remove_alert, list_currencies, check_alerts, main) مشابه کد اصلی باقی می‌مانند
# فقط در check_alerts باید pair_id را هم در نظر بگیریم:
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
