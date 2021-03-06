import pandas as pd
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
from apscheduler.schedulers.blocking import BlockingScheduler
from lib.BinanceAccount import BinanceAccount
from lib.Strategy import Strategy
import lib.conf as conf


def session():
    print(datetime.now().strftime("%d-%m-%Y %H:%M:%S,%f"))
    sell_signals_count = 0
    buy_signals_count = 0
    client = Client(api_key=conf.binance_apikey, api_secret=conf.binance_apisecret)

    '''
        get ticker data of market
        symbol_prices:    'BTCUSDT': xxxx.xx
    '''
    ticker_df = pd.DataFrame(client.get_ticker())
    symbol_prices = {}
    for pair_price in client.get_all_tickers():
        symbol_prices[pair_price['symbol']] = float(pair_price['price'])

    '''
        only pairs with USDT
        only pairs with volume > minimal volume of interest to trade
        only pairs not containing other quote asset than USDT
    '''
    filter_ticker_df = ticker_df['symbol'].str.contains('USDT')
    ticker_df = ticker_df[filter_ticker_df]
    filter_ticker_df = ticker_df['quoteVolume'].astype(float) > conf.minvolume_USDT
    ticker_df = ticker_df[filter_ticker_df]
    ignore_coins = ['USDC', 'PAX', 'BUSD', 'TUSD', 'USDS', 'BNB', 'MTL'] + conf.coins_to_ignore
    for coin in ignore_coins:
        filter_ticker_df = ticker_df['symbol'].str.contains(coin)
        ticker_df = ticker_df[~filter_ticker_df]

    trade_pairs = ticker_df['symbol'].tolist()
    trade_pairs = [pair for pair in trade_pairs if pair[-4:] == 'USDT']

    for pair in conf.coins_to_include:
        if pair not in trade_pairs:
            trade_pairs.append(pair)

        # for the Charts generator
    currencies = {}

    '''
    check if any pair meets criteria to be traded
    '''
    all_signals = []

    sell_signals = []
    buy_signals = []

    buy_dict = {}
    for pair in trade_pairs:
        if any([ignore in pair for ignore in ignore_coins]):
            continue
        signal = Strategy(pair)
        currencies[pair] = signal.symbol

        # run checks and execute sell order if met criteria
        if signal.is_hot_sell:
            sell_signals.append(pair)
            if pair not in all_signals:
                all_signals.append(pair)
            sell_signals_count += 1
            try:
                binance_account = BinanceAccount(conf.binance_apikey, conf.binance_apisecret)
                binance_account.start_sell_order(
                    symbol=pair,
                    latest_price=symbol_prices[pair],
                    lot_filter=signal.currency.lot_size
                )
            except BinanceAPIException as e:
                print(e.message)

        # run checks and execute buy order if met criteria
        if signal.is_hot_buy:
            buy_signals.append(pair)
            if pair not in all_signals:
                all_signals.append(pair)
            buy_signals_count += 1
            buy_dict[pair] = signal

    buy_list = [(val.checkable, key, val.currency.lot_size) for key, val in buy_dict.items()]

    for buy_sign in buy_list:
        try:
            binance_account = BinanceAccount(conf.binance_apikey, conf.binance_apisecret)
            tickers_raw = binance_account.client.get_orderbook_tickers()

            tickers_usdt = [
                tck_usdt for tck_usdt in tickers_raw if
                'USDT' in tck_usdt['symbol'] and not float(tck_usdt['bidPrice']) == 0
            ]

            for ticker in tickers_usdt:
                if ticker['symbol'] == buy_sign[1]:
                    diff = (float(ticker['askPrice']) / float(ticker['bidPrice']) - 1) * 100
                    if diff < 0.4:
                        binance_account.start_buy_order(
                            symbol=buy_sign[1],
                            latest_price=symbol_prices[buy_sign[1]],
                            lot_filter=buy_sign[2]
                        )

        except BinanceAPIException as e:
            print(e.message)


if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(session, 'cron', minute=0, second=5)
    scheduler.add_job(session, 'cron', minute=15, second=5)
    scheduler.add_job(session, 'cron', minute=30, second=5)
    scheduler.add_job(session, 'cron', minute=45, second=5)
    scheduler.start()