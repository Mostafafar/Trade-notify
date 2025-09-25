import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os
from dotenv import load_dotenv

# بارگذاری تنظیمات از فایل .env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', 'YOUR_CHAT_ID_HERE')
NOBITEX_BASE_URL = "https://api.nobitex.ir"

class NobitexAPI:
    def __init__(self):
        self.base_url = NOBITEX_BASE_URL
    
    def get_market_stats(self, symbol="USDTIRR"):
        """دریافت اطلاعات بازار برای یک نماد خاص"""
        try:
            url = f"{self.base_url}/v2/orderbook/{symbol}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching data from Nobitex: {e}")
            return None
    
    def get_all_markets(self):
        """دریافت لیست همه بازارها"""
        try:
            url = f"{self.base_url}/v2/orderbook/all"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching all markets: {e}")
            return None
    
    def get_price(self, symbol="USDTIRR"):
        """دریافت قیمت لحظه‌ای"""
        data = self.get_market_stats(symbol)
        if data and 'lastTrade' in data:
            return float(data['lastTrade']['price'])
        return None
    
    def get_bid_ask(self, symbol="USDTIRR"):
        """دریافت بهترین قیمت خرید و فروش"""
        data = self.get_market_stats(symbol)
        if data and 'bids' in data and 'asks' in data:
            best_bid = float(data['bids'][0][0])  # بالاترین قیمت خرید
            best_ask = float(data['asks'][0][0])  # پایینترین قیمت فروش
            return best_bid, best_ask
        return None, None

class TradeNotifyBot:
    def __init__(self):
        self.nobitex = NobitexAPI()
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """تنظیم هندلرهای دستورات"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("price", self.get_price))
        self.application.add_handler(CommandHandler("status", self.get_status))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("tether", self.get_tether_price))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع"""
        welcome_text = """
🤖 **ربات Trade Notify خوش آمدید**

📊 این ربات قیمت‌های لحظه‌ای ارزهای دیجیتال را از نوبیتکس دریافت می‌کند.

🔄 **دستورات موجود:**
/start - راهنمای ربات
/price - دریافت قیمت تتر
/price [نماد] - دریافت قیمت نماد خاص (مثال: /price BTCUSDT)
/tether - قیمت تتر به ریال
/status - وضعیت کلی بازار
/help - راهنمای دستورات

💰 **نمادهای پرطرفدار:**
USDTIRR - تتر به ریال
BTCUSDT - بیت‌کوین
ETHUSDT - اتریوم

✍️ توسعه داده شده توسط Mostafafar
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای دستورات"""
        help_text = """
📋 **راهنمای دستورات:**

/start - راهنمای اولیه ربات
/price - قیمت تتر به ریال
/price BTCUSDT - قیمت بیت‌کوین
/tether - قیمت تتر (همان /price)
/status - وضعیت کلی بازار

💡 **مثال‌ها:**
/price
/price ETHUSDT
/status
        """
        await update.message.reply_text(help_text)
    
    async def get_tether_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت قیمت تتر"""
        await self.get_price(update, context, "USDTIRR")
    
    async def get_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE, default_symbol="USDTIRR"):
        """دریافت قیمت"""
        symbol = default_symbol
        
        if context.args:
            symbol = context.args[0].upper()
        
        price = self.nobitex.get_price(symbol)
        bid, ask = self.nobitex.get_bid_ask(symbol)
        
        if price is None or bid is None or ask is None:
            await update.message.reply_text("❌ خطا در دریافت داده از نوبیتکس. لطفاً稍后再试")
            return
        
        if symbol == "USDTIRR":
            # فرمت ریال
            message = f"💵 **قیمت {symbol}**\n\n"
            message += f"💰 قیمت لحظه‌ای: `{price:,.0f}` ریال\n"
            message += f"🔼 بهترین خرید: `{bid:,.0f}` ریال\n"
            message += f"🔽 بهترین فروش: `{ask:,.0f}` ریال\n"
            message += f"📊 اسپرد: `{ask-bid:,.0f}` ریار"
            
            # تبدیل به تومان
            price_toman = price / 10
            message += f"\n💎 معادل: `{price_toman:,.0f}` تومان"
        else:
            # فرمت دلار
            message = f"💰 **قیمت {symbol}**\n\n"
            message += f"📈 قیمت لحظه‌ای: `{price:,.2f}` دلار\n"
            message += f"🔼 بهترین خرید: `{bid:,.2f}` دلار\n"
            message += f"🔽 بهترین فروش: `{ask:,.2f}` دلار\n"
            message += f"📊 اسپرد: `{ask-bid:.4f}` دلار"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def get_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """وضعیت کلی بازار"""
        try:
            # دریافت قیمت تتر اول
            usdt_price = self.nobitex.get_price("USDTIRR")
            
            if not usdt_price:
                await update.message.reply_text("❌ خطا در دریافت داده‌های بازار")
                return
            
            message = "📊 **وضعیت بازار نوبیتکس**\n\n"
            message += f"💵 قیمت تتر: `{usdt_price:,.0f}` ریال\n"
            message += f"💎 معادل تومان: `{usdt_price/10:,.0f}` تومان\n\n"
            message += "🔸 **قیمت ارزهای دیجیتال:**\n"
            
            # لیست ارزهای مهم برای نمایش
            important_pairs = [
                ('BTCUSDT', 'بیت‌کوین'),
                ('ETHUSDT', 'اتریوم'), 
                ('ADAUSDT', 'کاردانو'),
                ('DOTUSDT', 'پولکادات'),
                ('SOLUSDT', 'سولانا'),
                ('DOGEUSDT', 'دوج‌کوین')
            ]
            
            for pair, name in important_pairs:
                price = self.nobitex.get_price(pair)
                if price:
                    message += f"• {name}: `{price:,.2f}` دلار\n"
                else:
                    message += f"• {name}: ❌ خطا\n"
            
            message += "\n⏰ آخرین بروزرسانی: لحظه‌ای"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در دریافت وضعیت بازار: {str(e)}")
    
    def run(self):
        """اجرای ربات"""
        print("🤖 ربات Trade Notify در حال اجرا است...")
        print("🔄 ربات آماده دریافت دستورات است")
        print("💡 از دستور /start در تلگرام استفاده کنید")
        self.application.run_polling()

def main():
    """تابع اصلی اجرای برنامه"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ لطفاً توکن ربات تلگرام را در فایل .env تنظیم کنید")
        return
    
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID == 'YOUR_CHAT_ID_HERE':
        print("❌ لطفاً چت آیدی را در فایل .env تنظیم کنید")
        return
    
    print("🎯 Trade Notify Bot Starting...")
    print("📊 داده‌ها از نوبیتکس دریافت می‌شود")
    
    try:
        bot = TradeNotifyBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 ربات متوقف شد")
    except Exception as e:
        print(f"❌ خطا در اجرای ربات: {e}")

if __name__ == "__main__":
    main()
