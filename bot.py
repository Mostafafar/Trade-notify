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
BASE_URL = "https://publicapi.ramzinex.com"
TELEGRAM_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# کش برای ذخیره اطلاعات جفت‌ارزها
currency_cache = {}
cache_timestamp = 0
CACHE_TIMEOUT = 300  # 5 دقیقه

# دیتابیس برای ذخیره تنظیمات کاربران
def init_db():
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, currency TEXT, pair_id INTEGER, threshold REAL, 
                  last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency))''')
    conn.commit()
    conn.close()

def get_currency_pairs():
    """دریافت لیست جفت‌ارزها از API رمزینکس"""
    global currency_cache, cache_timestamp
    
    # بررسی کش
    current_time = datetime.now().timestamp()
    if currency_cache and (current_time - cache_timestamp) < CACHE_TIMEOUT:
        return currency_cache
    
    try:
        # استفاده از اندپوینت صحیح API برای مارکت‌ها
        response = requests.get(f"{BASE_URL}/exchange/api/v1.0/exchange/market", timeout=10)
        logger.info(f"Market API Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API Response type: {type(data)}")
            
            if isinstance(data, list):
                currency_mapping = {}
                pair_details = {}
                
                for market in data:
                    try:
                        market_id = market.get('id')
                        base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                        quote_currency = market.get('quote_asset', {}).get('symbol', '').upper()
                        
                        if market_id and base_currency:
                            currency_mapping[base_currency] = market_id
                            pair_details[market_id] = {
                                'base_currency': base_currency,
                                'quote_currency': quote_currency,
                                'name_fa': market.get('base_asset', {}).get('name_fa', 'N/A'),
                                'name_en': market.get('base_asset', {}).get('name_en', 'N/A'),
                                'last_price': market.get('last_price'),
                                'volume': market.get('volume'),
                                'change_percent': market.get('change_percent')
                            }
                            logger.info(f"Found market: {base_currency} -> {market_id}")
                    except Exception as e:
                        logger.warning(f"Error processing market data: {e}")
                        continue
                
                if currency_mapping:
                    currency_cache = {
                        'mapping': currency_mapping,
                        'details': pair_details
                    }
                    cache_timestamp = current_time
                    logger.info(f"Successfully loaded {len(currency_mapping)} currency pairs")
                    return currency_cache
                else:
                    logger.error("No valid currency pairs found in API response")
            
            elif isinstance(data, dict):
                logger.info(f"Dict structure: {list(data.keys())}")
                # اگر داده دیکشنری است، ساختارهای مختلف را بررسی می‌کنیم
                if 'data' in data and isinstance(data['data'], list):
                    # پردازش مشابه لیست
                    currency_mapping = {}
                    pair_details = {}
                    
                    for market in data['data']:
                        try:
                            market_id = market.get('id')
                            base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                            
                            if market_id and base_currency:
                                currency_mapping[base_currency] = market_id
                                pair_details[market_id] = {
                                    'base_currency': base_currency,
                                    'quote_currency': market.get('quote_asset', {}).get('symbol', '').upper(),
                                    'name_fa': market.get('base_asset', {}).get('name_fa', 'N/A'),
                                    'name_en': market.get('base_asset', {}).get('name_en', 'N/A')
                                }
                        except Exception as e:
                            logger.warning(f"Error processing market data: {e}")
                            continue
                    
                    if currency_mapping:
                        currency_cache = {
                            'mapping': currency_mapping,
                            'details': pair_details
                        }
                        cache_timestamp = current_time
                        logger.info(f"Successfully loaded {len(currency_mapping)} currency pairs from dict structure")
                        return currency_cache
        
        logger.error(f"API Error: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Response text: {response.text[:500]}")
        return None
            
    except Exception as e:
        logger.error(f"Error getting currency pairs: {e}")
        return None

def get_currency_pair_id(currency_symbol):
    """یافتن pair_id مربوط به یک ارز خاص"""
    pairs_data = get_currency_pairs()
    if not pairs_data:
        return None
    
    currency_symbol = currency_symbol.upper()
    return pairs_data['mapping'].get(currency_symbol)

def get_price(currency_symbol):
    """دریافت قیمت از رمزینکس"""
    try:
        currency_upper = currency_symbol.upper()
        
        # ابتدا از کش استفاده می‌کنیم
        pairs_data = get_currency_pairs()
        if pairs_data:
            # جستجو در جزئیات مارکت‌ها برای قیمت
            for pair_id, details in pairs_data['details'].items():
                if details.get('base_currency') == currency_upper:
                    price = details.get('last_price')
                    if price:
                        logger.info(f"Found price for {currency_symbol} in cache: {price}")
                        return float(price)
        
        # اگر در کش نبود، مستقیماً از API می‌گیریم
        response = requests.get(f"{BASE_URL}/exchange/api/v1.0/exchange/market", timeout=10)
        if response.status_code == 200:
            markets = response.json()
            
            if isinstance(markets, list):
                for market in markets:
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    if base_currency == currency_upper:
                        price = market.get('last_price')
                        if price:
                            logger.info(f"Found price for {currency_symbol}: {price}")
                            return float(price)
            
            elif isinstance(markets, dict) and 'data' in markets:
                for market in markets['data']:
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    if base_currency == currency_upper:
                        price = market.get('last_price')
                        if price:
                            logger.info(f"Found price for {currency_symbol}: {price}")
                            return float(price)
        
        logger.warning(f"No price found for {currency_symbol}")
        return None
            
    except Exception as e:
        logger.error(f"Error getting price for {currency_symbol}: {e}")
        return None

def get_all_currencies():
    """دریافت لیست تمام ارزهای قابل معامله"""
    pairs_data = get_currency_pairs()
    if not pairs_data:
        # لیست پیش‌فرض ارزهای معروف
        default_currencies = ['BTC', 'ETH', 'USDT', 'ADA', 'DOT', 'LTC', 'BCH', 'XRP', 'EOS', 'TRX']
        return default_currencies
    
    return sorted(pairs_data['mapping'].keys())

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
/info [ارز] - اطلاعات کامل یک ارز (مثال: `/info btc`)

💡 **مثال:**
`/set btc 5` - هشدار برای تغییر ۵٪ بیت‌کوین
`/set eth 10` - هشدار برای تغییر ۱۰٪ اتریوم

🔗 **پشتیبانی از صرافی رمزینکس**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def currency_info(update: Update, context: CallbackContext):
    """نمایش اطلاعات کامل یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/info btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    pairs_data = get_currency_pairs()
    
    if not pairs_data:
        await update.message.reply_text("❌ خطا در دریافت اطلاعات از سرور")
        return
    
    pair_id = get_currency_pair_id(currency)
    if not pair_id:
        await update.message.reply_text(f"❌ ارز {currency} یافت نشد.")
        return
    
    pair_detail = pairs_data['details'].get(pair_id, {})
    price = get_price(currency)
    
    info_text = f"💰 **اطلاعات ارز {currency}**\n\n"
    info_text += f"• شناسه: `{pair_id}`\n"
    info_text += f"• نام فارسی: {pair_detail.get('name_fa', 'N/A')}\n"
    info_text += f"• نام انگلیسی: {pair_detail.get('name_en', 'N/A')}\n"
    info_text += f"• ارز پایه: {pair_detail.get('base_currency', 'N/A')}\n"
    info_text += f"• ارز متقابل: {pair_detail.get('quote_currency', 'N/A')}\n"
    
    if price:
        info_text += f"• قیمت فعلی: {price:,.0f} تومان\n"
        
        # اطلاعات اضافی اگر موجود باشد
        change_percent = pair_detail.get('change_percent')
        volume = pair_detail.get('volume')
        
        if change_percent is not None:
            info_text += f"• تغییر 24h: {change_percent}%\n"
        if volume is not None:
            info_text += f"• حجم معاملات: {volume:,.0f}\n"
    else:
        info_text += "• قیمت فعلی: در دسترس نیست\n"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/test btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    await update.message.reply_text(f"🔍 در حال دریافت قیمت {currency}...")
    
    # تست API
    try:
        response = requests.get(f"{BASE_URL}/exchange/api/v1.0/exchange/market", timeout=10)
        logger.info(f"Direct API test - Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API Response type: {type(data)}")
            if isinstance(data, list):
                logger.info(f"Number of markets: {len(data)}")
                if len(data) > 0:
                    sample_market = data[0]
                    logger.info(f"Sample market keys: {list(sample_market.keys())}")
    except Exception as e:
        logger.error(f"Direct API test failed: {e}")
    
    price = get_price(currency)
    
    if price is not None:
        await update.message.reply_text(f"✅ قیمت {currency}: {price:,.0f} تومان")
    else:
        currencies = get_all_currencies()
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد یا خطا در دریافت قیمت.\n\n"
            f"✅ ارزهای موجود: {', '.join(currencies)}\n"
            f"لطفاً از حروف لاتین استفاده کنید (مثال: BTC به جای بیت‌کوین)"
        )

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
        currencies = get_all_currencies()
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد یا خطا در دریافت قیمت.\n\n"
            f"✅ ارزهای موجود: {', '.join(currencies)}\n"
            f"لطفاً از حروف لاتین استفاده کنید."
        )
        return
    
    pair_id = get_currency_pair_id(currency) or 1
    
    # ذخیره در دیتابیس
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
        if current_price and last_price:
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
            
            text += f"\n\n💡 برای اطلاعات کامل یک ارز از /info [ارز] استفاده کنید."
            text += f"\n📝 مثال: `/info btc`"
            
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها از سرور رمزینکس")
            
    except Exception as e:
        logger.error(f"Error in list_currencies: {e}")
        await update.message.reply_text("❌ خطا در ارتباط با سرور رمزینکس")

async def check_alerts(context: CallbackContext):
    """بررسی هشدارها هر 30 ثانیه"""
    try:
        conn = sqlite3.connect('notifications.db')
        c = conn.cursor()
        c.execute('SELECT user_id, currency, pair_id, threshold, last_price FROM alerts')
        alerts = c.fetchall()
        
        if not alerts:
            conn.close()
            return
        
        logger.info(f"Checking {len(alerts)} alerts...")
        
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
        
        logger.info("Starting bot...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
