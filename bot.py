import asyncio
from binance import AsyncClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
import logging
import warnings

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Conversation states
WAITING_COIN, WAITING_LEVERAGE, WAITING_ALLOCATION, WAITING_TARGET = range(4)

class TradingMonitorBot:
    def __init__(self):
        self.user_data = {}
        self.binance_client = None
        self.monitoring_tasks = {}
        self.application = None
        self.running = False

    async def init_clients(self, api_key=None, api_secret=None):
        """Initialize API clients"""
        self.binance_client = await AsyncClient.create(api_key, api_secret)
        return self

    async def cleanup(self):
        """Cleanup resources properly"""
        self.running = False
        
        # Cancel all monitoring tasks
        for user_id, task in self.monitoring_tasks.items():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self.monitoring_tasks.clear()
        
        if self.binance_client:
            await self.binance_client.close_connection()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        await update.message.reply_text(
            "👋 **Trading Monitor Bot**\n\n"
            "Available commands:\n"
            "/set_coin - Set cryptocurrency\n"
            "/set_leverage - Set leverage\n"
            "/set_alloc - Set allocation percentage\n"
            "/set_target - Set target percentage\n"
            "/start_monitor - Start monitoring\n"
            "/stop_monitor - Stop monitoring\n"
            "/status - Show current status",
            parse_mode='Markdown'
        )

    async def set_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set cryptocurrency to monitor"""
        await update.message.reply_text("Please enter the coin symbol (e.g. BTC or ETH):")
        return WAITING_COIN

    async def process_coin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process coin input"""
        coin = update.message.text.upper()
        if not coin.isalpha():
            await update.message.reply_text("⚠️ Please enter only letters (e.g. BTC)")
            return WAITING_COIN
            
        user_id = update.effective_user.id
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
            
        self.user_data[user_id]['coin'] = f"{coin}USDT"
        await update.message.reply_text(
            f"✅ {coin} set\n"
            f"Please set leverage with /set_leverage"
        )
        return ConversationHandler.END

    async def set_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set leverage"""
        await update.message.reply_text("Enter leverage amount (1-125):")
        return WAITING_LEVERAGE

    async def process_leverage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process leverage input"""
        try:
            leverage = float(update.message.text)
            if leverage < 1 or leverage > 125:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['leverage'] = leverage
            await update.message.reply_text(
                f"✅ Leverage {leverage}x set\n"
                f"Set allocation with /set_alloc"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number (1-125)")
            return WAITING_LEVERAGE

    async def set_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set allocation percentage"""
        await update.message.reply_text("Enter allocation percentage (0.1-100):")
        return WAITING_ALLOCATION

    async def process_allocation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process allocation input"""
        try:
            alloc = float(update.message.text)
            if alloc <= 0 or alloc > 100:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['allocation'] = alloc
            await update.message.reply_text(
                f"✅ Allocation {alloc}% set\n"
                f"Set target with /set_target"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid number (0.1-100)")
            return WAITING_ALLOCATION

    async def set_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set target percentage"""
        await update.message.reply_text("Enter target percentage change (e.g. 5 for 5%):")
        return WAITING_TARGET

    async def process_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process target input"""
        try:
            target = float(update.message.text)
            if target <= 0:
                raise ValueError
                
            user_id = update.effective_user.id
            self.user_data[user_id]['target_change'] = target
            
            await update.message.reply_text(
                f"✅ Settings complete:\n\n"
                f"Coin: {self.user_data[user_id]['coin']}\n"
                f"Leverage: {self.user_data[user_id].get('leverage', 1)}x\n"
                f"Allocation: {self.user_data[user_id].get('allocation', 100)}%\n"
                f"Target: {self.user_data[user_id].get('target_change', 5)}%\n\n"
                f"Start monitoring with /start_monitor"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid positive number")
            return WAITING_TARGET

    async def start_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start price monitoring"""
        user_id = update.effective_user.id
        if user_id not in self.user_data or 'coin' not in self.user_data[user_id]:
            await update.message.reply_text("⚠️ Please set coin first with /set_coin")
            return
            
        if user_id in self.monitoring_tasks and not self.monitoring_tasks[user_id].done():
            await update.message.reply_text("ℹ️ Monitoring already active")
            return
            
        self.user_data[user_id]['monitoring'] = True
        current_price = await self.get_current_price(user_id)
        if current_price is None:
            await update.message.reply_text("⚠️ Error getting initial price")
            return
            
        self.user_data[user_id]['last_price'] = current_price
        self.monitoring_tasks[user_id] = asyncio.create_task(self.monitor_price(user_id, context))
        
        await update.message.reply_text(
            f"🔍 Monitoring {self.user_data[user_id]['coin']} started\n"
            f"Alerting on {self.user_data[user_id].get('target_change', 5)}% changes "
            f"with {self.user_data[user_id].get('leverage', 1)}x leverage"
        )

    async def stop_monitor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop price monitoring"""
        user_id = update.effective_user.id
        if user_id in self.monitoring_tasks:
            self.monitoring_tasks[user_id].cancel()
            try:
                await self.monitoring_tasks[user_id]
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[user_id]
            
        if user_id in self.user_data:
            self.user_data[user_id]['monitoring'] = False
            
        await update.message.reply_text("⏹️ Monitoring stopped")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current status"""
        user_id = update.effective_user.id
        if user_id not in self.user_data or 'coin' not in self.user_data[user_id]:
            await update.message.reply_text("⚠️ No settings configured")
            return
            
        user_data = self.user_data[user_id]
        monitoring_status = "Active ✅" if user_data.get('monitoring', False) else "Inactive ❌"
        
        try:
            current_price = await self.get_current_price(user_id)
            price_info = f"Current price: {current_price:.8f}"
        except Exception:
            price_info = "Current price: Unknown"
        
        await update.message.reply_text(
            f"📊 Current status:\n\n"
            f"Coin: {user_data['coin']}\n"
            f"Leverage: {user_data.get('leverage', 1)}x\n"
            f"Allocation: {user_data.get('allocation', 100)}%\n"
            f"Target: {user_data.get('target_change', 5)}%\n"
            f"Monitoring: {monitoring_status}\n"
            f"{price_info}"
        )

    async def get_current_price(self, user_id):
        """Get current coin price"""
        try:
            ticker = await self.binance_client.get_symbol_ticker(
                symbol=self.user_data[user_id]['coin']
            )
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"Price error for {user_id}: {e}")
            return None

    async def monitor_price(self, user_id, context):
        """Monitor price changes"""
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
                
                leverage = self.user_data[user_id].get('leverage', 1)
                change = ((current_price - last_price) / last_price) * 100 * leverage
                target_change = self.user_data[user_id].get('target_change', 5)
                
                if abs(change) >= target_change:
                    direction = "📈 Up" if change > 0 else "📉 Down"
                    allocation = self.user_data[user_id].get('allocation', 100)
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🚨 Price Alert 🚨\n\n"
                            f"Coin: {self.user_data[user_id]['coin']}\n"
                            f"{direction} {abs(change):.2f}% (with {leverage}x)\n"
                            f"Allocation: {allocation}%\n\n"
                            f"Previous: {last_price:.8f}\n"
                            f"Current: {current_price:.8f}"
                        )
                    )
                    self.user_data[user_id]['last_price'] = current_price
                
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error for {user_id}: {e}")
                await asyncio.sleep(300)

async def run_bot():
    """Run the bot with proper resource management"""
    bot = TradingMonitorBot()
    bot.running = True
    
    try:
        # Initialize clients
        await bot.init_clients()
        
        # Create application
        application = Application.builder().token("7584437136:AAFVtfF9RjCyteONcz8DSg2F2CfhgQT2GcQ").build()
        bot.application = application
        
        # Add handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("status", bot.status))
        application.add_handler(CommandHandler("set_leverage", bot.set_leverage))
        application.add_handler(CommandHandler("set_alloc", bot.set_allocation))
        application.add_handler(CommandHandler("set_target", bot.set_target))
        application.add_handler(CommandHandler("start_monitor", bot.start_monitor))
        application.add_handler(CommandHandler("stop_monitor", bot.stop_monitor))

        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('set_coin', bot.set_coin)],
            states={
                WAITING_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_coin)],
                WAITING_LEVERAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_leverage)],
                WAITING_ALLOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_allocation)],
                WAITING_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_target)],
            },
            fallbacks=[]
        )
        application.add_handler(conv_handler)

        # Run polling in background
        polling_task = asyncio.create_task(application.run_polling())
        
        # Keep bot running
        while bot.running:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        # Cleanup resources
        try:
            if hasattr(bot, 'application') and bot.application:
                await bot.application.shutdown()
                await bot.application.stop()
            
            await bot.cleanup()
            
            # Cancel all remaining tasks
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

def main():
    """Main entry point"""
    # Create new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Cleanup loop
        if not loop.is_closed():
            loop.close()

if __name__ == "__main__":
    main()
