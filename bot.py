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
import requests
import threading

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

# کلاس مدیریت WebSocket
class RamzinexWebSocket:
    def __init__(self):
        self.connected = False
        self.price_data = {}
        self.market_mapping = {}
        self._stop_event = threading.Event()
        self.thread = None
        
    def start(self):
        """شروع WebSocket در یک thread جداگانه"""
        if self.thread and self.thread.is_alive():
            return
            
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.thread.start()
        logger.info("WebSocket thread started")
    
    def stop(self):
        """توقف WebSocket"""
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("WebSocket stopped")
    
    def _run_websocket(self):
        """اجرای WebSocket در thread جداگانه"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_loop())
    
    async def _websocket_loop(self):
        """حلقه اصلی WebSocket"""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)
    
    async def _connect_and_listen(self):
        """اتصال و گوش دادن به WebSocket"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WEBSOCKET_URL, heartbeat=30) as ws:
                    self.connected = True
                    logger.info("✅ Connected to Ramzinex WebSocket")
                    
                    # ارسال پیام connect
                    connect_msg = {'connect': {'name': 'python-bot'}, 'id': 1}
                    await ws.send_json(connect_msg)
                    logger.info("Sent connect message")
                    
                    # Initialize markets
                    await self._initialize_markets(ws)
                    
                    # گوش دادن به پیام‌ها
                    async for msg in ws:
                        if self._stop_event.is_set():
                            break
                            
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_websocket_message(msg.data, ws)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("WebSocket error occurred")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.info("WebSocket connection closed")
                            break
                            
        except Exception as e:
            self.connected = False
            logger.error(f"WebSocket connection failed: {e}")
            await asyncio.sleep(5)
    
    async def _initialize_markets(self, ws):
        """مقداردهی اولیه مارکت‌ها"""
        try:
            # دریافت لیست مارکت‌ها از API
            response = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=10)
            if response.status_code == 200:
                data = response.json()
                markets = data if isinstance(data, list) else data.get('data', [])
                
                subscribed_count = 0
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
                        await ws.send_json(subscribe_msg)
                        subscribed_count += 1
                        logger.debug(f"Subscribed to {base_currency} (ID: {market_id})")
                
                logger.info(f"✅ Subscribed to {subscribed_count} markets")
            else:
                logger.error(f"Failed to get markets: HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error initializing markets: {e}")
    
    async def _handle_websocket_message(self, message_data, ws):
        """مدیریت پیام‌های WebSocket"""
        try:
            data = json.loads(message_data)
            
            # پاسخ به ping
            if data == {}:
                await ws.send_json({})  # Pong
                return
            
            # پردازش پیام‌های publish
            if 'publish' in data:
                channel = data['publish'].get('channel', '')
                publication_data = data['publish'].get('data', {})
                
                if channel.startswith('last-trades:'):
                    market_id = channel.split(':')[1]
                    currency = self.market_mapping.get(market_id)
                    if currency and 'trades' in publication_data and publication_data['trades']:
                        latest_trade = publication_data['trades'][-1]
                        price = float(latest_trade.get('price', 0))
                        
                        if price > 0:
                            self.price_data[currency] = {
                                'price': price,
                                'timestamp': datetime.now().timestamp(),
                                'volume': latest_trade.get('volume', 0)
                            }
                            logger.debug(f"📊 {currency} price update: {price:,.0f}")
            
            # لاگ کردن اتصال موفق
            if 'connect' in data and data['connect'].get('client'):
                logger.info("✅ WebSocket authenticated successfully")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON message from WebSocket")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    def get_price(self, currency_symbol):
        """دریافت قیمت یک ارز"""
        currency = currency_symbol.upper()
        
        # اول از داده‌های WebSocket استفاده می‌کنیم
        if currency in self.price_data:
            price_info = self.price_data[currency]
            # بررسی که داده بیشتر از 2 دقیقه قدیمی نباشد
            if datetime.now().timestamp() - price_info['timestamp'] < 120:
                return price_info['price']
        
        # fallback به API معمولی
        return self._get_price_from_api(currency)
    
    def _get_price_from_api(self, currency_symbol):
        """دریافت قیمت از API معمولی"""
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
            logger.error(f"API price fetch error for {currency_symbol}: {e}")
            return None
    
    def get_all_currencies(self):
        """دریافت لیست تمام ارزها"""
        currencies = [curr for curr in self.market_mapping.keys() if curr.isalpha()]
        return sorted(currencies) if currencies else ['BTC', 'ETH', 'USDT', 'ADA', 'DOT', 'LTC', 'BCH', 'XRP', 'EOS', 'TRX']
    
    def get_connection_status(self):
        """دریافت وضعیت اتصال"""
        return self.connected

# ایجاد نمونه جهانی WebSocket
websocket_manager = RamzinexWebSocket()

# دستورات بات تلگرام
async def start(update: Update, context: CallbackContext):
    """دستور شروع"""
    status = "✅ متصل" if websocket_manager.get_connection_status() else "❌ قطع"
    
    welcome_text = f"""
🤖 **ربات اطلاع‌رسانی تغییرات قیمت رمزینکس**

وضعیت WebSocket: {status}

با این ربات می‌توانید برای تغییرات قیمت ارزهای مختلف در صرافی رمزینکس هشدار دریافت کنید.

📋 **دستورات موجود:**
/set [ارز] [درصد] - تنظیم هشدار (مثال: `/set btc 5`)
/list - نمایش هشدارهای فعال
/remove [ارز] - حذف هشدار (مثال: `/remove btc`)
/currencies - لیست ارزهای قابل دسترسی
/test [ارز] - تست دریافت قیمت (مثال: `/test btc`)
/status - وضعیت اتصال

💡 **مثال:**
`/set btc 5` - هشدار برای تغییر ۵٪ بیت‌کوین
`/set eth 10` - هشدار برای تغییر ۱۰٪ اتریوم

🔗 **پشتیبانی از داده‌های لحظه‌ای WebSocket**
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def status_command(update: Update, context: CallbackContext):
    """نمایش وضعیت اتصال"""
    status = "✅ متصل" if websocket_manager.get_connection_status() else "❌ قطع"
    currency_count = len(websocket_manager.get_all_currencies())
    active_alerts = await get_user_alerts_count(update.effective_user.id)
    
    status_text = f"""
📊 **وضعیت سیستم:**

• WebSocket: {status}
• تعداد ارزهای قابل دسترسی: {currency_count}
• هشدارهای فعال شما: {active_alerts}

💡 از دستور /test برای بررسی دریافت قیمت استفاده کنید.
"""
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def get_user_alerts_count(user_id):
    """شمارش هشدارهای کاربر"""
    try:
        conn = sqlite3.connect('notifications.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM alerts WHERE user_id = ?', (user_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

async def test_price(update: Update, context: CallbackContext):
    """تست دریافت قیمت"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ لطفاً اسم ارز را وارد کنید.\nمثال: `/test btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    await update.message.reply_text(f"🔍 در حال دریافت قیمت {currency}...")
    
    price = websocket_manager.get_price(currency)
    
    if price is not None:
        source = "WebSocket" if (currency in websocket_manager.price_data and 
                               datetime.now().timestamp() - websocket_manager.price_data[currency]['timestamp'] < 120) else "API"
        await update.message.reply_text(f"✅ قیمت {currency}: {price:,.0f} تومان\nمنبع: {source}")
    else:
        currencies = websocket_manager.get_all_currencies()[:10]  # فقط 10 ارز اول
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد.\n\n"
            f"🔸 نمونه ارزهای موجود: {', '.join(currencies)}\n"
            f"📋 برای دیدن لیست کامل از /currencies استفاده کنید."
        )

# سایر توابع (set_alert, list_alerts, remove_alert, list_currencies, currency_info, check_alerts)
# مانند قبل باقی می‌مانند، فقط از websocket_manager استفاده می‌کنند

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
    
    current_price = websocket_manager.get_price(currency)
    if current_price is None:
        currencies = websocket_manager.get_all_currencies()[:10]
        await update.message.reply_text(
            f"❌ ارز {currency} یافت نشد.\n\n"
            f"🔸 نمونه ارزهای موجود: {', '.join(currencies)}"
        )
        return
    
    pair_id = websocket_manager.market_mapping.get(currency, 1)
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT OR REPLACE INTO alerts 
                     (user_id, currency, pair_id, threshold, last_price) 
                     VALUES (?, ?, ?, ?, ?)''', 
                 (user_id, currency, pair_id, threshold, current_price))
        conn.commit()
        
        await update.message.reply_text(
            f"✅ هشدار تنظیم شد!\n\n"
            f"• ارز: {currency}\n"
            f"• درصد تغییر: {threshold}%\n"
            f"• قیمت فعلی: {current_price:,.0f} تومان"
        )
    except Exception as e:
        logger.error(f"Database error: {e}")
        await update.message.reply_text("❌ خطا در ذخیره‌سازی")
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
        await update.message.reply_text("❌ لطفاً اسم ارز را وارد کنید.\nمثال: `/remove btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    
    conn = sqlite3.connect('notifications.db')
    c = conn.cursor()
    c.execute('DELETE FROM alerts WHERE user_id = ? AND currency = ?', (user_id, currency))
    conn.commit()
    
    if c.rowcount > 0:
        await update.message.reply_text(f"✅ هشدار برای {currency} حذف شد.")
    else:
        await update.message.reply_text(f"❌ هشداری برای {currency} پیدا نشد.")
    
    conn.close()

async def list_currencies(update: Update, context: CallbackContext):
    """لیست ارزهای قابل دسترسی"""
    currencies = websocket_manager.get_all_currencies()
    
    if currencies:
        # تقسیم لیست به بخش‌های کوچکتر
        chunk_size = 20
        chunks = [currencies[i:i + chunk_size] for i in range(0, len(currencies), chunk_size)]
        
        for i, chunk in enumerate(chunks):
            text = f"💰 **ارزهای قابل دسترسی (بخش {i+1} از {len(chunks)}):**\n\n"
            text += ", ".join(chunk)
            await update.message.reply_text(text, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ خطا در دریافت لیست ارزها")

async def currency_info(update: Update, context: CallbackContext):
    """اطلاعات یک ارز"""
    args = context.args
    
    if len(args) != 1:
        await update.message.reply_text("❌ لطفاً اسم ارز را وارد کنید.\nمثال: `/info btc`", parse_mode='Markdown')
        return
    
    currency = args[0].upper()
    price = websocket_manager.get_price(currency)
    pair_id = websocket_manager.market_mapping.get(currency)
    
    info_text = f"💰 **اطلاعات {currency}**\n\n"
    
    if pair_id:
        info_text += f"• شناسه بازار: `{pair_id}`\n"
    
    if price:
        info_text += f"• قیمت فعلی: {price:,.0f} تومان\n"
        
        # اطلاعات از WebSocket
        if currency in websocket_manager.price_data:
            ws_data = websocket_manager.price_data[currency]
            age = int(datetime.now().timestamp() - ws_data['timestamp'])
            info_text += f"• به‌روزرسانی: {age} ثانیه پیش\n"
            if ws_data['volume']:
                info_text += f"• حجم: {ws_data['volume']}\n"
    else:
        info_text += "• قیمت: در دسترس نیست\n"
    
    info_text += f"\n💡 برای تنظیم هشدار: `/set {currency} 5`"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')

async def check_alerts(context: CallbackContext):
    """بررسی هشدارها"""
    try:
        conn = sqlite3.connect('notifications.db')
        c = conn.cursor()
        c.execute('SELECT user_id, currency, threshold, last_price FROM alerts')
        alerts = c.fetchall()
        
        if not alerts:
            conn.close()
            return
        
        processed = 0
        for user_id, currency, threshold, last_price in alerts:
            current_price = websocket_manager.get_price(currency)
            if current_price and last_price:
                change_percent = ((current_price - last_price) / last_price) * 100
                
                if abs(change_percent) >= threshold:
                    try:
                        emoji = "📈" if change_percent > 0 else "📉"
                        message = f"{emoji} **هشدار {currency}**\nتغییر: {change_percent:+.1f}%\nقیمت: {current_price:,.0f} تومان"
                        
                        await context.bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                        c.execute('UPDATE alerts SET last_price = ? WHERE user_id = ? AND currency = ?',
                                 (current_price, user_id, currency))
                        processed += 1
                        
                    except Exception as e:
                        logger.error(f"Error sending alert: {e}")
        
        conn.commit()
        conn.close()
        
        if processed > 0:
            logger.info(f"Sent {processed} alerts")
            
    except Exception as e:
        logger.error(f"Error in check_alerts: {e}")

def main():
    """تابع اصلی"""
    init_db()
    
    try:
        # شروع WebSocket
        websocket_manager.start()
        
        # ایجاد application تلگرام
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # ثبت handlerها
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("set", set_alert))
        application.add_handler(CommandHandler("list", list_alerts))
        application.add_handler(CommandHandler("remove", remove_alert))
        application.add_handler(CommandHandler("currencies", list_currencies))
        application.add_handler(CommandHandler("test", test_price))
        application.add_handler(CommandHandler("info", currency_info))
        
        # تنظیم job برای بررسی هشدارها
        job_queue = application.job_queue
        job_queue.run_repeating(check_alerts, interval=30, first=10)
        
        logger.info("✅ Bot started successfully")
        logger.info("✅ WebSocket connection initialized")
        logger.info("✅ Job scheduler started (30 second intervals)")
        
        # اجرای بات
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        websocket_manager.stop()

if __name__ == '__main__':
    main()
