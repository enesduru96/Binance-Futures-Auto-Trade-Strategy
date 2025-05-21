
import requests, time, math, json, websocket, locale, imaplib, email

from datetime import datetime
from binance.enums import *
from email.header import decode_header

locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')

from lib import json_functions
from lib import binance_functions
from lib import technical_analysis
from lib.settings import email_username, email_password, last_checked_email_file
from lib._logger import log_trade, log_error


socket = "wss://fstream.binance.com/ws/solusdt@kline_15m"
api_url = "https://fapi.binance.com/fapi/v1/klines"
symbol = 'SOLUSDT'
interval = '15m'


def get_last_checked_email_id():
    try:
        with open(last_checked_email_file, "r") as file:
            return file.read().strip()
    except FileNotFoundError as error:
        log_error(error)
        return None
    
def save_last_checked_email_id(email_id):
    with open(last_checked_email_file, "w") as file:
        file.write(email_id)

def check_emails(currency: str, num_emails: int = 5):
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_username, email_password)
    mail.select("inbox")

    status, messages = mail.search(None, f'SUBJECT "Alarm: {currency}usdt_15m_machinelearning"')
    machine_learning_ids = messages[0].split()
    last_checked_id = get_last_checked_email_id()

    if len(machine_learning_ids) > 0:
        recent_email_ids = machine_learning_ids[-num_emails:]

        latest_email_id = None
        latest_date = None

        for email_id in recent_email_ids:
            status, msg_data = mail.fetch(email_id, "(BODY[HEADER.FIELDS (DATE)])")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            date_header = msg["Date"]
            email_date = email.utils.parsedate_to_datetime(date_header)

            if not latest_date or email_date > latest_date:
                latest_date = email_date
                latest_email_id = email_id
                print(latest_email_id)

        latest_machine_learning_id = latest_email_id

        if last_checked_id == latest_machine_learning_id.decode():
            print("ID already checked")
            return "NO_SIGNAL"

        save_last_checked_email_id(latest_machine_learning_id.decode())

        status, msg_data = mail.fetch(latest_machine_learning_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject, encoding = decode_header(msg["Subject"])[0]
        body = msg.get_payload(decode=True).decode()

        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        from_ = msg.get("From")

        body_parts = body.split("_")
        signal_tone = abs(int(body_parts[5]))
        if signal_tone < 20:
            print(f"[-] Low signal tone for: {currency}")
            return "LOW_SIGNAL"

        if "Buy" in body:
            return "LONG"

        elif "Sell" in body:
            return "SHORT"

        else:
            return None

    mail.logout()

def calculate_quantity(latest_price):
    current_margin = json_functions.get_current_margin()
    risk_percentage = json_functions.get_risk_percentage()
    risk_amount = (current_margin * risk_percentage) / 100
    quantity = risk_amount / latest_price
    quantity = math.floor(quantity)

    return quantity

def check_active_position():
    current_position = binance_functions.get_current_position()
    no_position = current_position == None

    if no_position:
        position_size = 0
    else:
        position_size = float(current_position['positionAmt'])
    
    active_long_position = position_size > 0
    active_short_position = position_size < 0


    trading_status = json_functions.get_trading_status()
    if trading_status == "stop_trading":
        reference_price = json_functions.get_reference_price()
        latest_close = binance_functions.get_latest_closed_candle()

        if latest_close >= reference_price * 1.04 or latest_close <= reference_price * 0.96:
            json_functions.set_trading_status("continue")
            json_functions.reset_consecutive_losses()
            json_functions.set_reference_price(None)
        else:
            return "[-] After 3 consecutive losses, waiting for the price to have a new trend."
        
    else:

        ema_data = technical_analysis.get_EMAs()
        ema100 = ema_data['ema_100']
        latest_price = json_functions.get_latest_closed_candle()

        if active_long_position:
            entry_price = float(current_position['entryPrice'])
            quantity = abs(float(current_position['positionAmt']))

            if ((latest_price > ema100) and (latest_price <= entry_price * 0.95)) or (latest_price < ema100 * 0.985):
                order = binance_functions.close_long_MARKET_order()
                print(order)
                trade_data = binance_functions.get_last_closed_trade()
                log_trade(trade_data, "LONG STOPPED - (Below EMA100 or dropped too much)")
                json_functions.handle_closed_trade(trade_data)

        elif active_short_position:
            entry_price = float(current_position['entryPrice'])
            quantity = abs(float(current_position['positionAmt']))

            if ((latest_price < ema100) and latest_price >= entry_price * 1.02) or (latest_price > ema100 * 1.012):
                order = binance_functions.close_short_MARKET_order()
                print(order)
                trade_data = binance_functions.get_last_closed_trade()
                log_trade(trade_data, "SHORT STOPPED - (Above EMA100 or price increased too much)")
                json_functions.handle_closed_trade(trade_data)


        time.sleep(30)
        indicator_result = check_emails("sol")

        if indicator_result == "LONG":
            print(f"Starting long process.")
            if technical_analysis.rsi_oversold():

                print(position_size)

                buy_signal = latest_price > ema100

                if buy_signal:
                    if active_short_position:
                        order = binance_functions.close_short_MARKET_order(position_size)
                        print(order)
                        trade_data = binance_functions.get_last_closed_trade()
                        log_trade(trade_data, "Got long signal, reversing from short.")
                        json_functions.handle_closed_trade(trade_data)
                    if not active_long_position:
                        latest_price = binance_functions.get_current_price()
                        quantity = calculate_quantity(latest_price)
                        long_order = binance_functions.open_long_MARKET_order(quantity)
                        trade_data = binance_functions.get_last_closed_trade()
                        log_trade(trade_data, "Got long signal, longed.")
                        entry_price = float(trade_data["price"])
                        take_profit = round(entry_price * 1.011, 3)
                        print(f"LONG - Entry Price: {entry_price} - Take Profit: {take_profit}")
                        
                        take_profit_order = binance_functions.set_take_profit_LONG(quantity, take_profit)
                        print(take_profit_order)

            else:
                print("RSI SAYS WAIT")

        elif indicator_result == "SHORT":
            print(f"Starting short process.")
            if technical_analysis.rsi_overbought():

                print(position_size)

                short_signal = latest_price < ema100

                if short_signal:
                    if active_long_position:
                        order = binance_functions.close_long_MARKET_order(position_size)
                        print(order)
                        trade_data = binance_functions.get_last_closed_trade()
                        log_trade(trade_data, "Got short signal, reversing from long.")
                    if not active_short_position:
                        latest_price = binance_functions.get_current_price()
                        quantity = calculate_quantity(latest_price)
                        short_order = binance_functions.open_short_MARKET_order(quantity)
                        trade_data = binance_functions.get_last_closed_trade()
                        log_trade(trade_data, "Got short signal, shorted.")
                        entry_price = float(trade_data["price"])
                        take_profit = round(entry_price * 0.968, 3)
                        stop_loss = round(entry_price * 1.015, 3)
                        print(f"SHORT - Entry Price: {entry_price} - Take Profit: {take_profit} - Stop Loss: {stop_loss}")
                        
                        take_profit_order = binance_functions.set_take_profit_LONG(quantity, take_profit)
                        print(take_profit_order)

                        stop_loss_order = binance_functions.set_stop_loss_SHORT_MARKET(quantity, stop_loss)
                        print(stop_loss_order)


            else:
                print("RSI SAYS WAIT")
        
        else:
            print(f"MachineLearning Indicator Result: {indicator_result}")



def fetch_latest_closed_kline():
    try:
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': 2
        }
        response = requests.get(api_url, params=params)
        klines = response.json()
        
        if klines:
            last_closed_kline = klines[-2]
            close_time = datetime.fromtimestamp(last_closed_kline[6] / 1000.0)
            formatted_time = close_time.strftime('%d-%m-%Y %H:%M')
            
            kline_data = {
                'symbol': symbol,
                'interval': interval,
                'open': last_closed_kline[1],
                'close': last_closed_kline[4],
                'high': last_closed_kline[2],
                'low': last_closed_kline[3],
                'volume': last_closed_kline[5],
                'number_of_trades': last_closed_kline[8],
                'closed': True,
                'timestamp': formatted_time
            }
            with open('latest_kline.json', 'w', encoding='utf-8') as f:
                json.dump(kline_data, f, ensure_ascii=False, indent=4)
            print(f"Initial kline data updated at {formatted_time}")
        
    except Exception as e:
        print(f"Error fetching initial kline data: {e}")


def update_latest_kline(data):
    kline = data['k']
    close_time = datetime.fromtimestamp(kline['T'] / 1000.0)
    formatted_time = close_time.strftime('%d-%m-%Y %H:%M')
    kline_data = {
        'symbol': kline['s'],
        'interval': kline['i'],
        'open': kline['o'],
        'close': kline['c'],
        'high': kline['h'],
        'low': kline['l'],
        'volume': kline['v'],
        'number_of_trades': kline['n'],
        'closed': kline['x'],
        'timestamp': formatted_time
    }
    with open('latest_kline.json', 'w', encoding='utf-8') as f:
        json.dump(kline_data, f, ensure_ascii=False, indent=4)
    print(f"Kline data updated at {formatted_time}")


def on_message(ws, message):
    data = json.loads(message)
    kline = data['k']
    is_candle_closed = kline['x']
    if is_candle_closed:
        update_latest_kline(data)
        result = check_active_position()
        print(result)


def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket is closed")

def on_open(ws):
    print("WebSocket is open")

def main():
    try:
        check_active_position()
        fetch_latest_closed_kline()
        ws = websocket.WebSocketApp(socket,
                                    on_open=on_open,
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
        ws.run_forever()
    except Exception as err:
        print(f"Error on main: {err}")

if __name__ == "__main__":
    main()