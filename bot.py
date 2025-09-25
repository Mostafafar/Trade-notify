import requests
import time
from datetime import datetime
import logging

# تنظیمات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class CryptoPriceBot:
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.supported_coins = {
            'bitcoin': 'BTC',
            'ethereum': 'ETH', 
            'tether': 'USDT',
            'binancecoin': 'BNB',
            'ripple': 'XRP',
            'cardano': 'ADA'
        }
    
    def get_price(self, coin_id='bitcoin', currency='usd'):
        """دریافت قیمت ارز دیجیتال از CoinGecko"""
        try:
            url = f"{self.base_url}/simple/price"
            params = {
                'ids': coin_id,
                'vs_currencies': currency,
                'include_24hr_change': 'true'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if coin_id in data:
                price = data[coin_id].get(currency, 0)
                change_24h = data[coin_id].get(f'{currency}_24h_change', 0)
                
                return {
                    'success': True,
                    'coin': coin_id,
                    'symbol': self.supported_coins.get(coin_id, coin_id.upper()),
                    'price': price,
                    'currency': currency.upper(),
                    'change_24h': round(change_24h, 2),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                return {'success': False, 'error': 'Coin not found'}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching price: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_multiple_prices(self, coin_ids=None, currency='usd'):
        """دریافت قیمت چند ارز به صورت همزمان"""
        if coin_ids is None:
            coin_ids = ['bitcoin', 'ethereum', 'tether']
        
        try:
            coin_ids_str = ','.join(coin_ids)
            url = f"{self.base_url}/simple/price"
            params = {
                'ids': coin_ids_str,
                'vs_currencies': currency,
                'include_24hr_change': 'true'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for coin_id in coin_ids:
                if coin_id in data:
                    coin_data = data[coin_id]
                    results.append({
                        'coin': coin_id,
                        'symbol': self.supported_coins.get(coin_id, coin_id.upper()),
                        'price': coin_data.get(currency, 0),
                        'currency': currency.upper(),
                        'change_24h': round(coin_data.get(f'{currency}_24h_change', 0), 2)
                    })
            
            return {'success': True, 'data': results}
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching multiple prices: {e}")
            return {'success': False, 'error': str(e)}
    
    def format_price_message(self, price_data):
        """قالب‌بندی پیام قیمت برای نمایش زیبا"""
        if not price_data['success']:
            return f"❌ خطا در دریافت قیمت: {price_data.get('error', 'Unknown error')}"
        
        symbol = price_data['symbol']
        price = price_data['price']
        currency = price_data['currency']
        change = price_data['change_24h']
        timestamp = price_data['timestamp']
        
        # انتخاب ایموجی بر اساس تغییرات قیمت
        if change > 0:
            trend_emoji = "📈"
        elif change < 0:
            trend_emoji = "📉"
        else:
            trend_emoji = "➡️"
        
        # فرمت‌بندی قیمت
        if price > 1000:
            formatted_price = f"{price:,.0f}"
        elif price > 1:
            formatted_price = f"{price:,.2f}"
        else:
            formatted_price = f"{price:.6f}"
        
        message = f"""
{trad_emoji} **{symbol} ({price_data['coin'].capitalize()})**

💰 قیمت: **{formatted_price} {currency}**
{tend_emoji} تغییر 24h: **{change}%**
⏰ زمان: {timestamp}
        """
        
        return message
    
    def format_multiple_prices_message(self, prices_data):
        """قالب‌بندی پیام برای چند ارز"""
        if not prices_data['success']:
            return f"❌ خطا در دریافت قیمت‌ها: {prices_data.get('error', 'Unknown error')}"
        
        message = "🏪 **قیمت‌های بازار کریپتو**\n\n"
        
        for coin in prices_data['data']:
            symbol = coin['symbol']
            price = coin['price']
            currency = coin['currency']
            change = coin['change_24h']
            
            # انتخاب ایموجی
            if change > 0:
                trend_emoji = "📈"
            elif change < 0:
                trend_emoji = "📉"
            else:
                trend_emoji = "➡️"
            
            # فرمت‌بندی قیمت
            if price > 1000:
                formatted_price = f"{price:,.0f}"
            elif price > 1:
                formatted_price = f"{price:,.2f}"
            else:
                formatted_price = f"{price:.6f}"
            
            message += f"{trend_emoji} **{symbol}**: {formatted_price} {currency} ({change}%)\n"
        
        message += f"\n⏰ آخرین بروزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return message

def main():
    """تابع اصلی برای تست ربات"""
    bot = CryptoPriceBot()
    
    print("🤖 ربات تست قیمت‌های کریپتو راه‌اندازی شد!")
    print("=" * 50)
    
    # تست دریافت قیمت تک ارز
    print("\n1. تست دریافت قیمت بیت‌کوین:")
    btc_price = bot.get_price('bitcoin', 'usd')
    print(bot.format_price_message(btc_price))
    
    # تست دریافت قیمت اتریوم
    print("\n2. تست دریافت قیمت اتریوم:")
    eth_price = bot.get_price('ethereum', 'usd')
    print(bot.format_price_message(eth_price))
    
    # تست دریافت چند قیمت
    print("\n3. تست دریافت چند قیمت:")
    coins = ['bitcoin', 'ethereum', 'tether', 'binancecoin']
    multiple_prices = bot.get_multiple_prices(coins, 'usd')
    print(bot.format_multiple_prices_message(multiple_prices))
    
    # تست خطا (ارز ناموجود)
    print("\n4. تست خطا (ارز ناموجود):")
    error_test = bot.get_price('invalid_coin', 'usd')
    print(bot.format_price_message(error_test))

if __name__ == "__main__":
    main()
