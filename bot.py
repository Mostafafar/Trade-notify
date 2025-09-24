#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import sqlite3
from datetime import datetime
import json
from centrifuge import Centrifuge

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
        self.client = None
        self.connected = False
        self.subscriptions = {}
        self.price_data = {}
        self.market_mapping = {}
        
    async def connect(self):
        """اتصال به WebSocket رمزینکس"""
        try:
            self.client = Centrifuge(WEBSOCKET_URL, {})
            
            # تعریف event handlers
            self.client.on("connected", self.on_connected)
            self.client.on("disconnected", self.on_disconnected)
            self.client.on("error", self.on_error)
            
            # شروع اتصال
            self.client.connect()
            logger.info("Connecting to Ramzinex WebSocket...")
            
        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {e}")
    
    def on_connected(self, ctx):
        """Handler برای زمانی که اتصال برقرار شد"""
        self.connected = True
        logger.info("Connected to Ramzinex WebSocket")
        
        # دریافت لیست مارکت‌ها و subscribe کردن
        asyncio.create_task(self.subscribe_to_markets())
    
    def on_disconnected(self, ctx):
        """Handler برای قطع اتصال"""
        self.connected = False
        logger.warning("Disconnected from Ramzinex WebSocket")
    
    def on_error(self, ctx):
        """Handler برای خطاها"""
        logger.error(f"WebSocket error: {ctx}")
    
    async def subscribe_to_markets(self):
        """Subscribe به کانال‌های قیمتی"""
        try:
            # ابتدا مارکت‌ها را از API معمولی دریافت می‌کنیم
            import requests
            response = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=10)
            
            if response.status_code == 200:
                markets = response.json()
                market_list = markets if isinstance(markets, list) else markets.get('data', [])
                
                for market in market_list:
                    market_id = market.get('id')
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    
                    if market_id and base_currency:
                        self.market_mapping[base_currency] = market_id
                        self.market_mapping[str(market_id)] = base_currency
                        
                        # Subscribe به کانال last-trades برای دریافت قیمت‌های لحظه‌ای
                        channel_name = f"last-trades:{market_id}"
                        await self.subscribe_to_channel(channel_name, base_currency)
                        
                logger.info(f"Subscribed to {len(self.market_mapping)//2} markets")
                
        except Exception as e:
            logger.error(f"Error subscribing to markets: {e}")
    
    async def subscribe_to_channel(self, channel_name, currency):
        """Subscribe به یک کانال خاص"""
        try:
            sub = self.client.new_subscription(channel_name, {"delta": "fossil"})
            
            @sub.on("publication")
            def on_message(ctx):
                self.handle_price_update(currency, ctx.data)
            
            @sub.on("subscribed")
            def on_subscribed(ctx):
                logger.debug(f"Subscribed to {channel_name}")
            
            @sub.on("error")
            def on_error(ctx):
                logger.error(f"Subscription error for {channel_name}: {ctx}")
            
            sub.subscribe()
            self.subscriptions[channel_name] = sub
            
        except Exception as e:
            logger.error(f"Error subscribing to {channel_name}: {e}")
    
    def handle_price_update(self, currency, data):
        """پردازش به روزرسانی قیمت"""
        try:
            if isinstance(data, dict) and 'trades' in data:
                trades = data['trades']
                if trades and len(trades) > 0:
                    latest_trade = trades[-1]  # آخرین معامله
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
            logger.error(f"Error handling price update for {currency}: {e}")
    
    def get_price(self, currency_symbol):
        """دریافت قیمت از داده‌های WebSocket"""
        currency = currency_symbol.upper()
        
        if currency in self.price_data:
            price_info = self.price_data[currency]
            # بررسی که داده بیشتر از 30 ثانیه قدیمی نباشد
            if datetime.now().timestamp() - price_info['timestamp'] < 30:
                return price_info['price']
        
        # اگر داده WebSocket قدیمی یا موجود نبود، از API معمولی استفاده می‌کنیم
        return self.get_price_from_api(currency)
    
    def get_price_from_api(self, currency_symbol):
        """دریافت قیمت از API معمولی (fallback)"""
        try:
            import requests
            currency = currency_symbol.upper()
            
            response = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/market", timeout=5)
            if response.status_code == 200:
                markets = response.json()
                market_list = markets if isinstance(markets, list) else markets.get('data', [])
                
                for market in market_list:
                    base_currency = market.get('base_asset', {}).get('symbol', '').upper()
                    if base_currency == currency:
                        price = market.get('last_price')
                        if price:
                            return float(price)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting price from API for {currency}: {e}")
            return None
    
    def get_all_currencies(self):
        """دریافت لیست تمام ارزهای قابل معامله"""
        currencies = []
        for currency, market_id in self.market_mapping.items():
            if currency.isalpha():  # فقط اسم ارزها (نه IDها)
                currencies.append(currency)
        return sorted(currencies) if currencies else ['BTC', 'ETH', 'USDT', 'ADA', 'DOT', 'LTC', 'BCH', 'XRP', 'EOS', 'TRX']

# ایجاد نمونه WebSocket جهانی
websocket_manager = RamzinexWebSocket()

# دستورات بات تلگرام (مانند قبل با تغییرات جزئی)
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
        source = "WebSocket" if currency in websocket_manager.price_data else "API"
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

async def list_currencies(update: Update, context: CallbackContext):
    """لیست ارزهای قابل دسترسی"""
    try:
        currencies = websocket_manager.get_all_currencies()
        
        if currencies:
            text = f"💰 **ارزهای قابل دسترسی ({len(currencies)} ارز):**\n\n"
            text += ", ".join(currencies)
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ خطا در دریافت لیست ارزها")
            
    except Exception as e:
        logger.error(f"Error in list_currencies: {e}")
        await update.message.reply_text("❌ خطا در ارتباط با سرور")

# سایر توابع (list_alerts, remove_alert, currency_info, check_alerts) 
# مانند قبل باقی می‌مانند با این تفاوت که از websocket_manager.get_price() استفاده می‌کنند

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

def main():
    """تابع اصلی"""
    init_db()
    
    try:
        # راه‌اندازی WebSocket در یک task جداگانه
        asyncio.create_task(websocket_manager.connect())
        
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
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()
