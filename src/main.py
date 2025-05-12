import json
import logging
import os
from decimal import ROUND_DOWN, Decimal

import dotenv
from binance import client

dotenv.load_dotenv()

# 定價策略: 
# - 取最近 1 天、4 小時、1 小時、30 分鐘、15 分鐘的平均成交價
# - 然後再取最新的成交價 (3 分鐘)
# - 抓價格最低的那一組，乘以 99.8%
# - 即為掛單買入價

# ------------------------------------------------------------------
#                             CONSTANT
# ------------------------------------------------------------------
THIS_DIR = os.path.dirname(__file__)
THIS_FILE_NAME_WITHOUT_EXT = os.path.splitext(os.path.basename(__file__))[0]
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")
CONFIG = json.load(open(os.path.join(PROJECT_ROOT, "config.json")))
PORTFOLIO: dict[str, float] = CONFIG['portfolio']
QUOTE: str = CONFIG['quote']
AMOUNT: float = CONFIG['amount']
# ------------------------------------------------------------------
#                              LOGGER
# ------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s %(levelname)s] %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
file_handler = logging.FileHandler(os.path.join(PROJECT_ROOT, f'{THIS_FILE_NAME_WITHOUT_EXT}.log'), encoding='utf-8')
stream_handler = logging.StreamHandler()
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
# ------------------------------------------------------------------
#                              CLIENT
# ------------------------------------------------------------------
client = client.Client(API_KEY, API_SECRET)
# ------------------------------------------------------------------
#                           TRADING PAIR
# ------------------------------------------------------------------
minQty: dict[str, Decimal] = {}
stepSize: dict[str, Decimal] = {}
tickSize: dict[str, Decimal] = {}
# ------------------------------------------------------------------

def check_config()-> None:
    if sum(PORTFOLIO.values()) == 100:
        logger.info("✅ portfolio 設置正確 (所有幣種加總起來的購買比例剛好等於 100%)")        
    else:
        raise Exception("portfolio 設置錯誤, 所有幣種加總起來的購買比例必須等於 100")
    
    for base in PORTFOLIO.keys():
        symbol_info = client.get_symbol_info(symbol=f"{base}{QUOTE}")
        
        if symbol_info is None:
            raise Exception(f"portfolio 設置錯誤, {base}/{QUOTE} 不是有效的交易對")
        else:
            logger.info(f"✅ portfolio 設置正確 ({base}/{QUOTE} 交易對存在)")
                
        if symbol_info.get('status') != 'TRADING':
            raise Exception(f"portfolio 設置錯誤, {base}/{QUOTE} 無法交易")
        else:
            logger.info(f"✅ portfolio 設置正確 ({base}/{QUOTE} 交易對可交易)")
        
        if 'LIMIT_MAKER' not in symbol_info.get('orderTypes'):
            raise Exception(f"portfolio 設置錯誤, {base}/{QUOTE} 無法掛單")
        else:
            logger.info(f"✅ portfolio 設置正確 ({base}/{QUOTE} 交易對可掛單)")

def check_env()-> None:
    if API_KEY is None or API_SECRET is None:
        raise Exception("幣安 API Key 或 Secret 未設置, 請檢查 .env 是否設置正確")
    else:
        logger.info("✅ 已設置幣安 API Key 與 Secret")
    
    if len(API_KEY) != 64 or len(API_SECRET) != 64:
        raise Exception("無效的幣安 API Key 或 Secret, 請檢查 .env 是否設置正確")
    else:
        logger.info("✅ 已確認幣安 API Key 與 Secret 格式正確")
    
    system_status = client.get_system_status()
    
    if system_status.get('status') != 0 or system_status.get('msg') != 'normal':
        raise Exception("幣安服務器連線異常, 請檢查本地網路狀態或幣安服務器是否維修中")
    else:
        logger.info("✅ 幣安服務器連線正常")

def set_market_settings()-> None:
    for base in PORTFOLIO.keys():
        symbol_info = client.get_symbol_info(symbol=f"{base}{QUOTE}")

        filter_price = next(f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER')
        filter_lot_size = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')

        tickSize[base] = Decimal(filter_price['tickSize']).normalize()
        minQty[base] = Decimal(filter_lot_size['minQty']).normalize()
        stepSize[base] = Decimal(filter_lot_size['stepSize']).normalize()

def get_free_balance(asset: str)-> float:
    balance = client.get_asset_balance(asset=asset).get('free')
    
    if balance is None:
        raise Exception(f"無法取得 {asset} 的資產可用餘額")
    else:
        balance = float(balance)

    logger.info(f'🔎 現貨帳戶中 {asset} 可動用交易餘額為 {balance} {asset}')

    return balance
    
def get_earn_balance(asset: str)-> float:
    resp = client.get_simple_earn_flexible_product_position(asset=asset)
    rows = resp.get('rows', [])
    
    if len(rows) != 1:
        raise Exception(f"無法取得 {asset} 的活期賺幣帳戶資訊")
    
    totalAmount = float(rows[0].get('totalAmount', '0.0'))
    canRedeem = rows[0].get('canRedeem')

    if canRedeem is False:
        raise Exception(f"{asset} 的活期賺幣帳戶餘額無法提取")
    
    return totalAmount
    
def redeem_earn_product(asset: str, amount: float)-> bool:
    resp = client.redeem_simple_earn_flexible_product(productId=f'{asset}001', amount=amount)
    suc = resp.get('success')
    
    if suc is None or not suc:
        raise Exception(f'提取 {asset} 的活期賺幣帳戶餘額 {amount} 失敗')
    
    return True

def get_avg_price(asset: str, quote: str, interval: str)-> float:
    assert interval in {'1s', '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'}, 'Invalid interval'
    
    symbol = f'{asset}{quote}'
    
    resp = client.get_klines(symbol=symbol, interval=interval, limit=1)
    
    if len(resp) != 1:
        raise Exception(f"無法取得 {symbol} 的 {interval} K線圖")
    elif len(resp[0]) != 12:
        raise Exception(f"無法取得 {symbol} 的 {interval} K線圖")

    high = float(resp[0][2])
    low = float(resp[0][3])
    close = float(resp[0][4])

    avg_price = float(Decimal((high+low+close)/3).quantize(tickSize[asset], rounding=ROUND_DOWN))
    
    return avg_price

def main():
    logger.info(f"{' 檢查錢包餘額 ':=^70}")
    
    free_balance = get_free_balance(QUOTE)
    
    if free_balance < AMOUNT:
        logger.info(f'⚠️ 現貨帳戶中 {QUOTE} 可動用交易餘額不足 {AMOUNT-free_balance} {QUOTE}')
        
        earn_balance = get_earn_balance(QUOTE)
        logger.info(f'🔎 活期賺幣帳戶中 {QUOTE} 可贖回餘額為 {earn_balance} {QUOTE}')
        
        if free_balance+earn_balance < AMOUNT:
            raise Exception(f'現貨帳戶與賺幣帳戶中 {QUOTE} 可動用餘額不足, 請充值後再重試')
        else:
            logger.info(f'↔️ 正在從活期賺幣帳戶中贖回 {AMOUNT-free_balance} {QUOTE}')
            redeem_earn_product(QUOTE, AMOUNT-free_balance)
            logger.info("✅ 活期賺幣帳戶贖回成功")
    else:
        logger.info("✅ 現貨帳戶可動用交易餘額足夠")
        
    for base, proportion in PORTFOLIO.items():
        logger.info(f'ℹ️ 預期從現貨帳戶中購買 {proportion}% {base} = {AMOUNT*(proportion/100)} {QUOTE}')
        
    logger.info(f"{' 定價策略與掛單 ':=^70}")
    
    for base, proportion in PORTFOLIO.items():
        if proportion == 0:
            continue

        one_day_avg_price = get_avg_price(base, QUOTE, '1d')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 1 日均價為 {one_day_avg_price} {QUOTE}')
        
        four_hours_avg_price = get_avg_price(base, QUOTE, '4h')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 4 小時均價為 {four_hours_avg_price} {QUOTE}')
        
        one_hour_avg_price = get_avg_price(base, QUOTE, '1h')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 1 小時均價為 {one_hour_avg_price} {QUOTE}')
        
        half_hour_avg_price = get_avg_price(base, QUOTE, '30m')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 30 分鐘均價為 {half_hour_avg_price} {QUOTE}')
        
        fifteen_mins_avg_price = get_avg_price(base, QUOTE, '15m')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 15 分鐘均價為 {fifteen_mins_avg_price} {QUOTE}')
        
        latest_price = get_avg_price(base, QUOTE, '3m')
        logger.info(f'👁️ 目前 {base}/{QUOTE} 的 3 分鐘均價為 {latest_price} {QUOTE}')
        
        if latest_price > min(one_day_avg_price, four_hours_avg_price, one_hour_avg_price, half_hour_avg_price, fifteen_mins_avg_price):
            maker_price = Decimal(latest_price * 0.998).quantize(Decimal(tickSize[base]), rounding=ROUND_DOWN)
            logger.info(f'📈 目前 {base}/{QUOTE} 的最新成交價呈現走強趨勢')
            logger.info(f'🧮 掛單價格調整為 {maker_price} {QUOTE}')

        else:
            maker_price = Decimal(min(one_day_avg_price, four_hours_avg_price, one_hour_avg_price, half_hour_avg_price, fifteen_mins_avg_price) * 0.998).quantize(Decimal(tickSize[base]), rounding=ROUND_DOWN)
            logger.info(f'📉 目前 {base}/{QUOTE} 的最新成交價呈現走弱趨勢')
            logger.info(f'🧮 掛單價格調整為 {maker_price} {QUOTE}')

        logger.info('-' * 60)
        
        quantity = Decimal(AMOUNT*(proportion/100) / float(maker_price)).quantize(Decimal(10) ** -abs(stepSize[base].as_tuple().exponent), rounding=ROUND_DOWN)
        
        logger.info(f'🚧 正在嘗試建立限價買入單 {base}/{QUOTE}...')
        logger.info(f'➡️ 買入價: {maker_price} {QUOTE}')
        logger.info(f'➡️ 買入數量: {quantity} {base}')
        
        resp = client.create_order(symbol=f"{base}{QUOTE}", side='BUY', type='LIMIT_MAKER', quantity=quantity, price=f'{maker_price}')
        orderId = resp.get('orderId')
        
        if orderId:
            logger.info('✅ 建立限價買入單成功')
        else:
            logger.info('❌ 建立限價買入單失敗')
            
        logger.info('-' * 60)
        
if __name__ == "__main__":
    logger.info(f"{' 檢查啟動環境 ':=^70}")
    check_env()
    check_config()
    set_market_settings()
    main()
    