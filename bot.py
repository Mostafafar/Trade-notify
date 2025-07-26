import os
import asyncio
import logging
from datetime import datetime
from weexsdk import WeexSDK
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class WeexTradingBot:
    def __init__(self):
        # Get config from environment variables
        self.weex_api_key = os.getenv('WEEX_API_KEY')
        self.weex_api_secret = os.getenv('WEEX_API_SECRET')
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.admin_chat_id = os.getenv('ADMIN_CHAT_ID')
        
        # Initialize clients
        self.weex = WeexSDK(api_key=self.weex_api_key, api_secret=self.weex_api_secret)
        self.tg_bot = Bot(token=self.telegram_token)
        
        # Trading parameters
        self.leverage = 2
        self.base_size = 100  # USDT
        self.profit_target = 0.05  # 5%
        self.cascade_target = 0.10  # 10%
        self.stop_loss = 0.10  # 10%
        
        # State tracking
        self.coins = []
        self.positions = {}
        self.cascade_levels = {}

    async def send_message(self, text: str):
        """Send formatted Telegram message"""
        try:
            await self.tg_bot.send_message(
                chat_id=self.admin_chat_id,
                text=text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def monitor_positions(self):
        """Main monitoring loop"""
        while True:
            try:
                for coin in self.coins:
                    await self.check_coin(coin)
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(300)

    async def check_coin(self, coin: str):
        """Check single coin's position"""
        try:
            ticker = self.weex.get_ticker(symbol=f"{coin}USDT")
            price = float(ticker['last_price'])
            
            if coin in self.positions:
                pos = self.positions[coin]
                entry = pos['entry_price']
                pnl = (entry - price)/entry if pos['type'] == 'short' else (price - entry)/entry
                
                if pnl >= self.profit_target and coin not in self.cascade_levels:
                    await self.handle_profit(coin, "initial")
                elif pnl >= self.cascade_target and coin in self.cascade_levels:
                    await self.handle_profit(coin, "cascade")
                elif pnl <= -self.stop_loss:
                    await self.handle_loss(coin)
                    
        except Exception as e:
            logger.error(f"Coin check failed for {coin}: {e}")

    async def handle_profit(self, coin: str, level: str):
        """Handle profit target hit"""
        try:
            idx = self.coins.index(coin)
            if idx + 1 < len(self.coins):
                next_coin = self.coins[idx + 1]
                price = self.get_price(next_coin)
                
                await self.place_order(
                    symbol=f"{next_coin}USDT",
                    side="sell",
                    quantity=self.base_size * self.leverage / price
                )
                
                self.cascade_levels[coin] = level
                msg = (
                    f"🎯 *{coin} hit {5 if level=='initial' else 10}% profit!*\n\n"
                    f"⚡ Opening short on {next_coin} at {self.leverage}x"
                )
                await self.send_message(msg)
                
        except Exception as e:
            logger.error(f"Profit handling failed: {e}")

    async def handle_loss(self, coin: str):
        """Handle stop loss"""
        try:
            if coin in self.cascade_levels:
                pos = self.positions[coin]
                close_size = pos['size'] * 0.5
                
                await self.place_order(
                    symbol=f"{coin}USDT",
                    side="buy" if pos['type'] == 'short' else "sell",
                    quantity=close_size
                )
                
                self.positions[coin]['size'] *= 0.5
                await self.send_message(
                    f"⚠️ *Stop Loss Triggered!*\n\n"
                    f"📉 {coin} dropped 10%, closed 50% position"
                )
                
        except Exception as e:
            logger.error(f"Loss handling failed: {e}")

    async def place_order(self, symbol: str, side: str, quantity: float):
        """Place order on WEEX"""
        try:
            return self.weex.create_order(
                symbol=symbol,
                side=side,
                type="market",
                quantity=quantity,
                leverage=self.leverage
            )
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return None

    def get_price(self, coin: str) -> float:
        """Get current price"""
        ticker = self.weex.get_ticker(symbol=f"{coin}USDT")
        return float(ticker['last_price'])

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *WEEX Trading Bot*\n\n"
        "Send 3 coin symbols to start (e.g. `PEPE FLOKI SHIBA`)",
        parse_mode='Markdown'
    )

async def handle_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coins = update.message.text.upper().split()
        if len(coins) != 3:
            await update.message.reply_text("Please send exactly 3 coin symbols")
            return
            
        bot = context.bot_data.setdefault('trading_bot', WeexTradingBot())
        bot.coins = coins
        
        # Open initial position
        first_coin = coins[0]
        price = bot.get_price(first_coin)
        await bot.place_order(
            symbol=f"{first_coin}USDT",
            side="sell",
            quantity=bot.base_size * bot.leverage / price
        )
        
        bot.positions[first_coin] = {
            'entry_price': price,
            'size': bot.base_size * bot.leverage / price,
            'type': 'short'
        }
        
        await bot.send_message(
            f"🎬 *Strategy Started!*\n\n"
            f"First position: {first_coin} short at ${price:.8f}\n"
            f"Next target: {coins[1]} at 5% profit"
        )
        
        # Start monitoring
        asyncio.create_task(bot.monitor_positions())
        
    except Exception as e:
        logger.error(f"Coin setup failed: {e}")
        await update.message.reply_text("Error starting strategy")

def main():
    # Verify environment variables
    required_vars = ['WEEX_API_KEY', 'WEEX_API_SECRET', 'TELEGRAM_TOKEN', 'ADMIN_CHAT_ID']
    for var in required_vars:
        if var not in os.environ:
            logger.error(f"Missing environment variable: {var}")
            return
    
    # Start bot
    application = Application.builder().token(os.getenv('8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8')).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coins))
    application.run_polling()

if __name__ == "__main__":
    main()
