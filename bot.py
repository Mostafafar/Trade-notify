import asyncio
from binance import AsyncClient
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TradingMonitorBot:
    def __init__(self):
        self.user_data = {}
        self.binance_client = None
        self.bot = None
        self.monitoring_tasks = {}

    async def init_clients(self):
        """Initialize API clients"""
        self.binance_client = await AsyncClient.create()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        await update.message.reply_text(
            "👋 **Leveraged Trading Monitor Bot**\n\n"
            "Available commands:\n"
            "/set_coin - Set cryptocurrency\n"
            "/set_leverage - Set leverage\n"
            "/set_alloc - Set allocation\n"
            "/set_target - Set target percentage\n"
            "/start_monitor - Start monitoring\n"
            "/stop_monitor - Stop monitoring",
            parse_mode='Markdown'
        )

    async def set_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set cryptocurrency to monitor"""
        await update.message.reply_text("Enter the coin symbol (e.g., BTC or ETH):")
        return 'WAITING_COIN'

    async def process_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process coin input"""
        coin = update.message.text.upper()
        self.user_data[update.effective_user.id] = {
            'coin': f"{coin}USDT",
            'leverage': 1,
            'allocation': 100,
            'target_change': 5,
            'monitoring': False
        }
        await update.message.reply_text(f"✅ {coin} set\nUse /set_leverage to set leverage")
        return -1

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set leverage"""
        await update.message.reply_text("Enter leverage amount (e.g., 2 for 2x):")
        return 'WAITING_LEVERAGE'

    async def process_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process leverage input"""
        try:
            leverage = float(update.message.text)
            if leverage < 1 or leverage > 125:
                raise ValueError
            self.user_data[update.effective_user.id]['leverage'] = leverage
            await update.message.reply_text(f"✅ {leverage}x leverage set\nUse /set_alloc to set allocation")
            return -1
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number (1-125)")
            return 'WAITING_LEVERAGE'

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set allocation percentage"""
        await update.message.reply_text("Enter allocation percentage (e.g., 50 for 50%):")
        return 'WAITING_ALLOCATION'

    async def process_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process allocation input"""
        try:
            alloc = float(update.message.text)
            if alloc <= 0 or alloc > 100:
                raise ValueError
            self.user_data[update.effective_user.id]['allocation'] = alloc
            await update.message.reply_text(f"✅ {alloc}% allocation set\nUse /set_target to set target")
            return -1
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid percentage (0-100)")
            return 'WAITING_ALLOCATION'

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target percentage change"""
        await update.message.reply_text("Enter target percentage change (e.g., 5 for 5%):")
        return 'WAITING_TARGET'

    async def process_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process target input"""
        try:
            target = float(update.message.text)
            if target <= 0:
                raise ValueError
            self.user_data[update.effective_user.id]['target_change'] = target
            user_data = self.user_data[update.effective_user.id]
            
            await update.message.reply_text(
                f"✅ Settings complete:\n\n"
                f"🏷️ Coin: {user_data['coin']}\n"
                f"📊 Leverage: {user_data['leverage']}x\n"
                f"💰 Allocation: {user_data['allocation']}%\n"
                f"🎯 Target change: {user_data['target_change']}%\n\n"
                f"Use /start_monitor to begin"
            )
            return -1
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid positive number")
            return 'WAITING_TARGET'

    async def get_current_price(self, user_id):
        """Get current price of the coin"""
        try:
            ticker = await self.binance_client.get_symbol_ticker(
                symbol=self.user_data[user_id]['coin']
            )
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Price error: {e}")
            return None

    async def monitor_task(self, user_id):
        """Background monitoring task"""
        while self.user_data.get(user_id, {}).get('monitoring', False):
            try:
                current_price = await self.get_current_price(user_id)
                if current_price is None:
                    await asyncio.sleep(60)
                    continue
                
                last_price = self.user_data[user_id].get('last_price')
                if last_price is None:
                    self.user_data[user_id]['last_price'] = current_price
                    await asyncio.sleep(60)
                    continue
                
                leverage = self.user_data[user_id]['leverage']
                change = ((current_price - last_price) / last_price) * 100 * leverage
                
                if abs(change) >= self.user_data[user_id]['target_change']:
                    direction = "📈 Up" if change > 0 else "📉 Down"
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🚨 Alert: {abs(change):.2f}% change ({direction})\n"
                            f"Coin: {self.user_data[user_id]['coin']}\n"
                            f"Leverage: {leverage}x\n"
                            f"Previous: {last_price:.8f}\n"
                            f"Current: {current_price:.8f}"
                        )
                    )
                    self.user_data[user_id]['last_price'] = current_price
                
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(300)

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start monitoring"""
        user_id = update.effective_user.id
        if user_id not in self.user_data:
            await update.message.reply_text("⚠️ Please complete setup first")
            return
        
        if self.user_data[user_id].get('monitoring'):
            await update.message.reply_text("⚠️ Monitoring already active")
            return

        self.user_data[user_id]['monitoring'] = True
        self.user_data[user_id]['last_price'] = await self.get_current_price(user_id)
        
        # Create and store monitoring task
        task = asyncio.create_task(self.monitor_task(user_id))
        self.monitoring_tasks[user_id] = task
        
        await update.message.reply_text(
            f"🔍 Monitoring {self.user_data[user_id]['coin']} started\n"
            f"Alerts at {self.user_data[user_id]['target_change']}% changes"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop monitoring"""
        user_id = update.effective_user.id
        if user_id in self.user_data and self.user_data[user_id].get('monitoring'):
            self.user_data[user_id]['monitoring'] = False
            
            # Cancel monitoring task if exists
            if user_id in self.monitoring_tasks:
                self.monitoring_tasks[user_id].cancel()
                try:
                    await self.monitoring_tasks[user_id]
                except asyncio.CancelledError:
                    pass
                del self.monitoring_tasks[user_id]
            
            await update.message.reply_text("⏹️ Monitoring stopped")
        else:
            await update.message.reply_text("⚠️ No active monitoring to stop")

async def main():
    """Main application"""
    monitor_bot = TradingMonitorBot()
    await monitor_bot.init_clients()
    
    application = Application.builder().token("8000378956:AAGfDy2R8tcUR_LcOTEfgTv8fAca512IgJ8").build()
    monitor_bot.bot = application.bot

    # Add handlers
    handlers = [
        CommandHandler("start", monitor_bot.start),
        CommandHandler("set_coin", monitor_bot.set_coin),
        CommandHandler("set_leverage", monitor_bot.set_leverage),
        CommandHandler("set_alloc", monitor_bot.set_allocation),
        CommandHandler("set_target", monitor_bot.set_target),
        CommandHandler("start_monitor", monitor_bot.start_monitor),
        CommandHandler("stop_monitor", monitor_bot.stop_monitor),
        MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_bot.process_coin, pattern='WAITING_COIN'),
        MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_bot.process_leverage, pattern='WAITING_LEVERAGE'),
        MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_bot.process_allocation, pattern='WAITING_ALLOCATION'),
        MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_bot.process_target, pattern='WAITING_TARGET')
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Bot started successfully")
        while True:
            await asyncio.sleep(3600)  # Keep running
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        if application.updater:
            await application.updater.stop()
        if application:
            await application.stop()
            await application.shutdown()
        if monitor_bot.binance_client:
            await monitor_bot.binance_client.close_connection()
        logger.info("Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
