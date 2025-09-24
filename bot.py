#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import sqlite3
from datetime import datetime
import requests  # اضافه کردن requests برای fallback sync

# تنظیمات
TELEGRAM_TOKEN = "8000378956:AAGCV0la1WKApWSmVXxtA5o8Q6KqdwBjdqU"
WEBSOCKET_URL = "wss://websocket.ramzinex.com/websocket"

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
                 (user_id INTEGER, currency TEXT, pair_id INTEGER, threshold REAL, 
                  last_price REAL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (user_id, currency))''')
    conn.commit()
    conn.close()

# کلاس مدیریت WebSocket با aiohttp
class RamzinexWebSocket:
    def __init__(self):
        self.session = None
        self.ws = None
        self.connected = False
        self.price_data = {}
        self.market_mapping = {}
        self.reconnect_delay = 5
        self.loop = None
        
    def set_loop(self, loop):
        """تنظیم event loop برای استفاده در توابع sync"""
        self.loop = loop
    
    async def connect(self):
        """اتصال به WebSocket رمزینکس"""
        while True:
            try:
                self.session = aiohttp.ClientSession()
                self.ws = await self.session.ws_connect(WEBSOCKET_URL)
                self.connected = True
                logger.info("Connected to Ramzinex WebSocket")
                
                # ارسال پیام connect
                connect_msg = {
                    'connect': {'name': 'python-client'},
                    'id': 1
                }
                await self.ws.send_json(connect_msg)
                
                # دریافت لیست مارکت‌ها و subscribe کردن
                await self.initialize_markets()
                
                # گوش دادن به پیام‌ها
                await self.listen()
                
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                self.connected = False
                if self.session:
                    await self.session.close()
                await asyncio.sleep(self.reconnect_delay)
    
    async def initialize_markets(self):
        """دریافت لیست مارکت‌ها و subscribe کردن"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        markets = data if isinstance(data, list) else data.get('data', [])
                        
                        for market in markets:
                            market_id = market.get('id')
                            base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                            
                            if market_id and base_currency:
                                self.market_mapping[base_currency] = market_id
                                self.market_mapping[str(market_id)] = base_currency
                                
                                # Subscribe به کانال last-trades
                                subscribe_msg = {
                                    'subscribe': {
                                        'channel': f'last-trades:{market_id}',
                                        'recover': True,
                                        'delta': 'fossil'
                                    },
                                    'id': market_id + 1000
                                }
                                await self.ws.send_json(subscribe_msg)
                                logger.debug(f"Subscribed to {base_currency} (ID: {market_id})")
                        
                        logger.info(f"Initialized {len(self.market_mapping)//2} markets")
                        
        except Exception as e:
            logger.error(f"Error initializing markets: {e}")
    
    async def listen(self):
        """گوش دادن به پیام‌های WebSocket"""
        async for msg in self.ws:
            try:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self.handle_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebSocket error")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket connection closed")
                    break
                    
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
    
    async def handle_message(self, data):
        """پردازش پیام‌های دریافتی"""
        try:
            # پاسخ به ping
            if data == {}:
                await self.ws.send_json({})  # Pong
                return
            
            # پردازش پیام‌های publication
            if 'publish' in data:
                channel = data.get('publish', {}).get('channel', '')
                publication_data = data.get('publish', {}).get('data', {})
                
                if channel.startswith('last-trades:'):
                    market_id = channel.split(':')[1]
                    currency = self.market_mapping.get(market_id)
                    if currency:
                        self.handle_trade_data(currency, publication_data)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def handle_trade_data(self, currency, data):
        """پردازش داده‌های معاملات"""
        try:
            if 'trades' in data and data['trades']:
                latest_trade = data['trades'][-1]  # آخرین معامله
                price = float(latest_trade.get('price', 0))
                
                if price > 0:
                    self.price_data[currency] = {
                        'price': price,
                        'timestamp': datetime.now().timestamp(),
                        'volume': latest_trade.get('volume', 0),
                        'type': latest_trade.get('type', 'unknown')
                    }
                    
                    logger.debug(f"Price update for {currency}: {price}")
                    
        except Exception as e:
            logger.error(f"Error handling trade data for {currency}: {e}")
    
    def get_price(self, currency_symbol):
        """دریافت قیمت از داده‌های WebSocket"""
        currency = currency_symbol.upper()
        
        if currency in self.price_data:
            price_info = self.price_data[currency]
            # بررسی که داده بیشتر از 60 ثانیه قدیمی نباشد
            if datetime.now().timestamp() - price_info['timestamp'] < 60:
                return price_info['price']
        
        # اگر داده WebSocket قدیمی یا موجود نبود، از API معمولی استفاده می‌کنیم
        return self.get_price_from_api_sync(currency)
    
    def get_price_from_api_sync(self, currency_symbol):
        """دریافت قیمت از API معمولی (fallback) - نسخه sync"""
        try:
            response = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=5)
            if response.status_code == 200:
                data = response.json()
                markets = data if isinstance(data, list) else data.get('data', [])
                
                for market in markets:
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    if base_currency == currency_symbol:
                        price = market.get('last_price')
                        if price:
                            return float(price)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting price from API for {currency_symbol}: {e}")
            return None
    
    async def get_price_from_api_async(self, currency_symbol):
        """دریافت قیمت از API معمولی (fallback) - نسخه async"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        markets = data if isinstance(data, list) else data.get('data', [])
                        
                        for market in markets:
                            base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                            if base_currency == currency_symbol:
                                price = market.get('last_price')
                                if price:
                                    return float(price)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting price from API for {currency_symbol}: {e}")
            return None
    
    def get_all_currencies(self):
        """دریافت لیست تمام ارزهای قابل معامله"""
        currencies = []
        for currency, market_id in self.market_mapping.items():
            if currency.isalpha():  # فقط اسم ارزها (نه IDها)
                currencies.append(currency)
        
        if not currencies:
            # Fallback به لیست پیش‌فرض اگر mapping خالی است
            return ['BTC', 'ETH', 'USDT', 'ADA', 'DOT', 'LTC', 'BCH', 'XRP', 'EOS', 'TRX']
        
        return sorted(currencies)

# ایجاد نمونه WebSocket جهانی
websocket_manager = RamzinexWebSocket()

# دستورات بات تلگرام
async def start(update: Update, context: CallbackContext):
    """دستور شروع"""
    welcome_text = """
🤖 **ربات اطلاع‌رسانی تغییرات قیمت رمزینکس (WebSocket)**

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

🔗 **پشتیبانی از WebSocket رمزینکس - داده‌های لحظه‌ای**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/test btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    price = websocket_manager.get_price(currency)
    
    if price is not None:
        source = "WebSocket" if (currency in websocket_manager.price_data and 
                               datetime.now().timestamp() - websocket_manager.price_data[currency]['timestamp'] < 60) else "API"
        await update.message.reply_text(f"✅ قیمت {currency}: {price:,.0f} تومان (منبع: {source})")
    else:
        currencies = websocket_manager.get_all_currencies()
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد یا خطا در دریافت قیمت.\n\n"
            f"✅ ارزهای موجود: {', '.join(currencies)}"
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
    current_price = websocket_manager.get_price(currency)
    if current_price is None:
        currencies = websocket_manager.get_all_currencies()
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد یا خطا در دریافت قیمت.\n\n"
            f"✅ ارزهای موجود: {', '.join(currencies)}"
        )
        return
    
    pair_id = websocket_manager.market_mapping.get(currency, 1)
    
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
        current_price = websocket_manager.get_price(currency)
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
        currencies = websocket_manager.get_all_currencies()
        
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

async def currency_info(update: Update, context: CallbackContext):
    """نمایش اطلاعات کامل یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ فرمت دستور نادرست است.\nمثال: `/info btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    price = websocket_manager.get_price(currency)
    pair_id = websocket_manager.market_mapping.get(currency)
    
    if not pair_id:
        # سعی می‌کنیم از API اطلاعات بگیریم
        try:
            response = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=5)
            if response.status_code == 200:
                data = response.json()
                markets = data if isinstance(data, list) else data.get('data', [])
                
                for market in markets:
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    if base_currency == currency:
                        pair_id = market.get('id')
                        name_fa = market.get('base_asset', {}).get('name_fa', 'N/A')
                        name_en = market.get('base_asset', {}).get('name_en', 'N/A')
                        quote_currency = market.get('quote_asset', {}).get('symbol', '').upper()
                        break
        except Exception as e:
            logger.error(f"Error getting currency info: {e}")
    
    if not pair_id:
        await update.message.reply_text(f"❌ ارز {currency} یافت نشد.")
        return
    
    info_text = f"💰 **اطلاعات ارز {currency}**\n\n"
    info_text += f"• شناسه بازار: `{pair_id}`\n"
    
    if 'name_fa' in locals():
        info_text += f"• نام فارسی: {name_fa}\n"
        info_text += f"• نام انگلیسی: {name_en}\n"
        info_text += f"• ارز متقابل: {quote_currency}\n"
    
    if price:
        info_text += f"• قیمت فعلی: {price:,.0f} تومان\n"
    else:
        info_text += "• قیمت فعلی: در دسترس نیست\n"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

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
            current_price = websocket_manager.get_price(currency)
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

async def start_websocket():
    """شروع اتصال WebSocket"""
    await websocket_manager.connect()

def main():
    """تابع اصلی"""
    init_db()
    
    try:
        # ایجاد event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # تنظیم loop برای websocket_manager
        websocket_manager.set_loop(loop)
        
        # راه‌اندازی WebSocket در پس‌زمینه
        loop.create_task(start_websocket())
        
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
        
        logger.info("Starting bot with WebSocket support...")
        
        # اجرای application در loop فعلی
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
