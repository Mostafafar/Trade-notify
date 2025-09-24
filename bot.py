#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import sqlite3
from datetime import datetime
import json

# تنظیمات
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
TELEGRAM_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# کش برای ذخیره اطلاعات ارزها
currency_cache = {}
cache_timestamp = 0
CACHE_TIMEOUT = 300  # 5 دقیقه

# دیتابیس برای ذخیره تنظیمات کاربران
def init_db():
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, currency_id TEXT, currency_symbol TEXT, 
                  threshold REAL, last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency_id))''')
    conn.commit()
    conn.close()

def get_coingecko_coin_list():
    """دریافت لیست ارزها از CoinGecko"""
    global currency_cache, cache_timestamp
    
    # بررسی کش
    current_time = datetime.now().timestamp()
    if currency_cache and (current_time - cache_timestamp) < CACHE_TIMEOUT:
        return currency_cache
    
    try:
        response = requests.get(f"{COINGECKO_API_URL}/coins/list", timeout=10)
        logger.info(f"CoinGecko API Status: {response.status_code}")
        
        if response.status_code == 200:
            coins = response.json()
            
            # ایجاد مپینگ برای جستجوی آسان
            coin_mapping = {}
            for coin in coins:
                coin_id = coin['id']
                symbol = coin['symbol'].upper()
                name = coin['name']
                
                coin_mapping[coin_id] = {
                    'symbol': symbol,
                    'name': name
                }
                
                # همچنین برای جستجو با سیمبل
                coin_mapping[symbol] = {
                    'id': coin_id,
                    'name': name
                }
            
            currency_cache = coin_mapping
            cache_timestamp = current_time
            logger.info(f"Successfully loaded {len(coins)} coins from CoinGecko")
            return currency_cache
            
        logger.error(f"CoinGecko API Error: {response.status_code}")
        return None
            
    except Exception as e:
        logger.error(f"Error getting coin list from CoinGecko: {e}")
        return None

def find_coin_id(symbol_or_name):
    """یافتن coin_id بر اساس سیمبل یا نام ارز"""
    coins_data = get_coingecko_coin_list()
    if not coins_data:
        return None
    
    symbol_or_name = symbol_or_name.lower()
    
    # جستجو در داده‌ها
    for coin_id, info in coins_data.items():
        if isinstance(info, dict):
            if info.get('symbol', '').lower() == symbol_or_name:
                return coin_id
            if info.get('name', '').lower() == symbol_or_name:
                return coin_id
    
    # اگر مستقیماً coin_id باشد
    if symbol_or_name in coins_data:
        return symbol_or_name
    
    return None

def get_price(coin_id):
    """دریافت قیمت از CoinGecko"""
    try:
        response = requests.get(
            f"{COINGECKO_API_URL}/simple/price", 
            params={
                'ids': coin_id,
                'vs_currencies': 'usd',
                'include_24hr_change': 'true'
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if coin_id in data:
                price_data = data[coin_id]
                return {
                    'usd': price_data.get('usd'),
                    'usd_24h_change': price_data.get('usd_24h_change')
                }
        
        logger.warning(f"No price found for {coin_id}")
        return None
            
    except Exception as e:
        logger.error(f"Error getting price for {coin_id}: {e}")
        return None

def get_all_popular_coins():
    """لیست ارزهای معروف"""
    popular_coins = [
        'bitcoin', 'ethereum', 'tether', 'binancecoin', 'ripple',
        'cardano', 'solana', 'dogecoin', 'polkadot', 'litecoin'
    ]
    
    coins_data = get_coingecko_coin_list()
    if not coins_data:
        return ['BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'ADA', 'SOL', 'DOGE', 'DOT', 'LTC']
    
    result = []
    for coin_id in popular_coins:
        if coin_id in coins_data:
            info = coins_data[coin_id]
            result.append(f"{info['symbol'].upper()} ({info['name']})")
    
    return result

async def start(update: Update, context: CallbackContext):
    """دستور شروع"""
    welcome_text = """
🤖 **ربات اطلاع‌رسانی تغییرات قیمت ارزهای دیجیتال**

با این ربات می‌توانید برای تغییرات قیمت ارزهای مختلف در CoinGecko هشدار دریافت کنید.

📋 **دستورات موجود:**
/set [ارز] [درصد] - تنظیم هشدار (مثال: `/set bitcoin 5` یا `/set btc 5`)
/list - نمایش هشدارهای فعال
/remove [ارز] - حذف هشدار (مثال: `/remove bitcoin`)
/currencies - لیست ارزهای معروف
/test [ارز] - تست دریافت قیمت یک ارز (مثال: `/test bitcoin`)
/info [ارز] - اطلاعات کامل یک ارز (مثال: `/info bitcoin`)

💡 **مثال:**
`/set bitcoin 5` - هشدار برای تغییر ۵٪ بیت‌کوین
`/set ethereum 10` - هشدار برای تغییر ۱۰٪ اتریوم

🔗 **داده‌ها از CoinGecko**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def currency_info(update: Update, context: CallbackContext):
    """نمایش اطلاعات کامل یک ارز"""
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/info bitcoin` یا `/info btc`", parse_mode='Markdown')
        return
    
    currency_input = ' '.join(args).lower()
    coin_id = find_coin_id(currency_input)
    
    if not coin_id:
        await update.message.reply_text(f"❌ ارز '{currency_input}' یافت نشد.")
        return
    
    coins_data = get_coingecko_coin_list()
    coin_info = coins_data.get(coin_id, {})
    price_data = get_price(coin_id)
    
    info_text = f"💰 **اطلاعات ارز دیجیتال**\n\n"
    info_text += f"• نام: {coin_info.get('name', 'N/A')}\n"
    info_text += f"• نماد: {coin_info.get('symbol', 'N/A').upper()}\n"
    info_text += f"• شناسه: `{coin_id}`\n"
    
    if price_data:
        price = price_data.get('usd')
        change_24h = price_data.get('usd_24h_change')
        
        if price:
            info_text += f"• قیمت فعلی: ${price:,.2f}\n"
        if change_24h is not None:
            info_text += f"• تغییر 24h: {change_24h:+.2f}%\n"
    else:
        info_text += "• قیمت فعلی: در دسترس نیست\n"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت یک ارز"""
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/test bitcoin` یا `/test btc`", parse_mode='Markdown')
        return
    
    currency_input = ' '.join(args).lower()
    
    await update.message.reply_text(f"🔍 در حال دریافت قیمت {currency_input}...")
    
    coin_id = find_coin_id(currency_input)
    
    if not coin_id:
        popular = get_all_popular_coins()
        await update.message.reply_text(
            f"❌ ارز '{currency_input}' یافت نشد.\n\n"
            f"✅ ارزهای معروف:\n" + "\n".join(popular) + 
            f"\n\n💡 می‌توانید از نام کامل (bitcoin) یا نماد (btc) استفاده کنید."
        )
        return
    
    price_data = get_price(coin_id)
    
    if price_data and price_data.get('usd'):
        coins_data = get_coingecko_coin_list()
        coin_info = coins_data.get(coin_id, {})
        
        price = price_data['usd']
        change_24h = price_data.get('usd_24h_change', 0)
        
        message = f"✅ **{coin_info.get('name', 'Unknown')} ({coin_info.get('symbol', '').upper()})**\n\n"
        message += f"• قیمت: ${price:,.2f}\n"
        message += f"• تغییر 24h: {change_24h:+.2f}%"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ خطا در دریافت قیمت")

async def set_alert(update: Update, context: CallbackContext):
    """تنظیم هشدار جدید"""
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/set bitcoin 5` یا `/set btc 5`", parse_mode='Markdown')
        return
    
    currency_input = ' '.join(args[:-1]).lower()
    threshold_str = args[-1]
    
    try:
        threshold = float(threshold_str)
        if threshold <= 0:
            await update.message.reply_text("❌ درصد باید بزرگتر از صفر باشد.")
            return
    except ValueError:
        await update.message.reply_text("❌ درصد باید یک عدد باشد.")
        return
    
    # یافتن coin_id
    coin_id = find_coin_id(currency_input)
    if not coin_id:
        popular = get_all_popular_coins()
        await update.message.reply_text(
            f"❌ ارز '{currency_input}' یافت نشد.\n\n"
            f"✅ ارزهای معروف:\n" + "\n".join(popular[:5])
        )
        return
    
    # دریافت قیمت فعلی
    price_data = get_price(coin_id)
    if not price_data or price_data.get('usd') is None:
        await update.message.reply_text("❌ خطا در دریافت قیمت فعلی")
        return
    
    current_price = price_data['usd']
    coins_data = get_coingecko_coin_list()
    coin_info = coins_data.get(coin_id, {})
    
    # ذخیره در دیتابیس
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT OR REPLACE INTO alerts 
                     (user_id, currency_id, currency_symbol, threshold, last_price) 
                     VALUES (?, ?, ?, ?, ?)''', 
                 (user_id, coin_id, coin_info.get('symbol', '').upper(), threshold, current_price))
        conn.commit()
        
        await update.message.reply_text(
            f"✅ هشدار تنظیم شد!\n"
            f"• ارز: {coin_info.get('name', coin_id)}\n"
            f"• نماد: {coin_info.get('symbol', '').upper()}\n"
            f"• درصد تغییر: {threshold}%\n"
            f"• قیمت فعلی: ${current_price:,.2f}\n\n"
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
    c.execute('SELECT currency_id, currency_symbol, threshold, last_price FROM alerts WHERE user_id = ?', (user_id,))
    alerts = c.fetchall()
    conn.close()
    
    if not alerts:
        await update.message.reply_text("📭 هیچ هشدار فعالی ندارید.")
        return
    
    text = "🔔 **هشدارهای فعال شما:**\n\n"
    for currency_id, currency_symbol, threshold, last_price in alerts:
        current_price_data = get_price(currency_id)
        
        if current_price_data and current_price_data.get('usd') and last_price:
            current_price = current_price_data['usd']
            change = ((current_price - last_price) / last_price) * 100
            text += f"• {currency_symbol}: {threshold}% (تغییر فعلی: {change:+.1f}%)\n"
        else:
            text += f"• {currency_symbol}: {threshold}% (خطا در دریافت قیمت)\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def remove_alert(update: Update, context: CallbackContext):
    """حذف هشدار"""
    user_id = update.effective_user.id
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/remove bitcoin` یا `/remove btc`", parse_mode='Markdown')
        return
    
    currency_input = ' '.join(args).lower()
    coin_id = find_coin_id(currency_input)
    
    if not coin_id:
        await update.message.reply_text(f"❌ ارز '{currency_input}' یافت نشد.")
        return
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('DELETE FROM alerts WHERE user_id = ? AND currency_id = ?', (user_id, coin_id))
    conn.commit()
    
    if c.rowcount > 0:
        await update.message.reply_text(f"✅ هشدار برای ارز '{currency_input}' حذف شد.")
    else:
        await update.message.reply_text(f"❌ هشداری برای ارز '{currency_input}' پیدا نشد.")
    
    conn.close()

async def list_currencies(update: Update, context: CallbackContext):
    """لیست ارزهای معروف"""
    try:
        popular_coins = get_all_popular_coins()
        
        text = "💰 **ارزهای دیجیتال معروف:**\n\n"
        text += "\n".join(popular_coins)
        
        text += f"\n\n💡 برای اطلاعات کامل یک ارز از /info [ارز] استفاده کنید."
        text += f"\n📝 مثال: `/info bitcoin` یا `/info btc`"
        
        await update.message.reply_text(text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in list_currencies: {e}")
        await update.message.reply_text("❌ خطا در ارتباط با سرور CoinGecko")

async def check_alerts(context: CallbackContext):
    """بررسی هشدارها هر 30 ثانیه"""
    try:
        conn = sqlite3.connect('notifications.db')
        c = conn.cursor()
        c.execute('SELECT user_id, currency_id, currency_symbol, threshold, last_price FROM alerts')
        alerts = c.fetchall()
        
        if not alerts:
            conn.close()
            return
        
        logger.info(f"Checking {len(alerts)} alerts...")
        
        for user_id, currency_id, currency_symbol, threshold, last_price in alerts:
            current_price_data = get_price(currency_id)
            
            if current_price_data and current_price_data.get('usd') and last_price:
                current_price = current_price_data['usd']
                change_percent = ((current_price - last_price) / last_price) * 100
                
                if abs(change_percent) >= threshold:
                    try:
                        emoji = "📈" if change_percent > 0 else "📉"
                        
                        message = (
                            f"{emoji} **هشدار قیمت ارز دیجیتال!**\n\n"
                            f"• ارز: {currency_symbol}\n"
                            f"• تغییر: {change_percent:+.1f}%\n"
                            f"• قیمت قبلی: ${last_price:,.2f}\n"
                            f"• قیمت فعلی: ${current_price:,.2f}\n"
                            f"• آستانه: {threshold}%\n"
                            f"• زمان: {datetime.now().strftime('%H:%M:%S')}"
                        )
                        
                        await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                        c.execute('UPDATE alerts SET last_price = ? WHERE user_id = ? AND currency_id = ?',
                                 (current_price, user_id, currency_id))
                        
                        logger.info(f"Alert sent to {user_id} for {currency_symbol}: {change_percent:.1f}%")
                        
                    except Exception as e:
                        logger.error(f"Error sending alert to {user_id}: {e}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error in check_alerts: {e}")

def main():
    """تابع اصلی"""
    init_db()
    
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("set", set_alert))
        application.add_handler(CommandHandler("list", list_alerts))
        application.add_handler(CommandHandler("remove", remove_alert))
        application.add_handler(CommandHandler("currencies", list_currencies))
        application.add_handler(CommandHandler("test", test_price))
        application.add_handler(CommandHandler("info", currency_info))
        
        job_queue = application.job_queue
        job_queue.run_repeating(check_alerts, interval=30, first=10)
        
        logger.info("Starting CoinGecko bot...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
