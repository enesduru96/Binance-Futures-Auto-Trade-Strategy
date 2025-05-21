# Binance Futures Auto Trade Strategy Bot
An automated futures trading bot depending on custom tradingview strategies and webhooks that I created and used for a few months


---

Subscribes to binance websocket and on every candle tick:

- Checks if there is a new email from tradingview (working similar to webhooks)
- Email has conditions like:
>no signal -> conditions are not met, no position is taken
>BUY -> signals to open a long position (reverse if there is a short position)
>SELL -> signals to open a short position (reverse if there is a long position)

- Checks current position of the account

- Changes its position depending on the incoming tradingview signals

---

Taking profit points are hard-coded, defined by trial-error

The bot uses EMAs, RSI together with some custom machine-learning tradingview strategies, taking into account multiple factors before creating a signal.

The strategy worked for over a few months and made some profit, besides being sold to a few customers. I stopped using it when crypto markets became unpredictable.