import logging
import yfinance as yf
import pandas as pd
import ta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

TOKEN = "7985446553:AAHubLt0uhPNxAonxEdKt87zRQT44Mp6ukk"

ASK_BALANCE, TRADING = range(2)
BALANCE = "balance"
WINS = "wins"
LOSSES = "losses"
PROFIT = "profit"
LAST_ACTION = "last_action"

ASSETS = {
    "يورو/دولار": "EURUSD=X",
    "Gold": "GC=F",
    "BTC/USD": "BTC-USD",
    "USDT/USD": "USDT-USD"
}

def fetch_signal(symbol):
    try:
        data = yf.download(symbol, period="2d", interval="1m")
    except Exception as e:
        logging.error(f"Error downloading data: {e}")
        return None

    if data is None or len(data) < 15:
        return None

    close = data['Close'].dropna()
    if len(close) < 15:
        return None

    ma = ta.trend.sma_indicator(close, window=10)
    rsi = ta.momentum.rsi(close, window=14)

    latest_price = float(close.iloc[-1])
    latest_ma = float(ma.iloc[-1])
    latest_rsi = float(rsi.iloc[-1])

    if latest_price > latest_ma and 55 < latest_rsi < 70:
        direction = "شراء"
        win_rate = 85
    elif latest_price < latest_ma and 30 < latest_rsi < 45:
        direction = "بيع"
        win_rate = 82
    else:
        direction = "لا تدخل"
        win_rate = 55

    market_good = not (47 <= latest_rsi <= 53)
    return {
        "symbol": symbol,
        "price": latest_price,
        "direction": direction,
        "win_rate": win_rate,
        "market_good": market_good
    }

def build_signal(asset_name, user_entry=10):
    asset_symbol = ASSETS[asset_name]
    sig = fetch_signal(asset_symbol)
    if not sig:
        return ("تعذر جلب بيانات السوق حالياً أو السوق مغلق. حاول مرة أخرى بعد قليل.", user_entry, 55, False)

    duration = "1 دقيقة"
    if sig["direction"] == "لا تدخل":
        advice = f"❌ نسبة النجاح: {sig['win_rate']}%\nلا تدخل الصفقة"
    elif sig["win_rate"] >= 70:
        advice = f"✅ نسبة النجاح: {sig['win_rate']}%"
    else:
        advice = f"⚠️ نسبة النجاح: {sig['win_rate']}%"

    market_status = "جيد" if sig["market_good"] else "السوق متذبذب لا ينصح بالتداول"
    signal = (
        f"صفقة جديدة ({asset_name})\n"
        f"🔻 . سعر السوق الحالي: {sig['price']}\n"
        f"⏱ . وقت الصفقة: {duration}\n"
        f"💸 . سعر دخول الصفقة: {user_entry}$\n"
        f"🔍 . {advice}\n"
        f"🪄 . السوق حاليا: {market_status}\n"
        f"اتجاه الصفقة: {sig['direction']}"
    )
    return signal, user_entry, sig["win_rate"], sig["market_good"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[BALANCE] = None
    context.user_data[WINS] = 0
    context.user_data[LOSSES] = 0
    context.user_data[PROFIT] = 0
    context.user_data[LAST_ACTION] = None
    await update.message.reply_text("مرحبًا! كم بحسابك في اكسبرت اوبشن الآن؟ (اكتب المبلغ فقط)")
    return ASK_BALANCE

async def set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = float(update.message.text.strip())
        context.user_data[BALANCE] = balance
        await update.message.reply_text(
            f"تم حفظ رصيدك: {balance} ريال.\nأرسل /signal لتحصل على أول صفقة."
        )
        return TRADING
    except ValueError:
        await update.message.reply_text("رجاءً أرسل المبلغ بالأرقام فقط.")
        return ASK_BALANCE

async def send_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(asset, callback_data=f"asset:{asset}")]
                for asset in ASSETS.keys()]
    await update.message.reply_text(
        "اختر العملة/الأصل المطلوب الحصول على إشارة له:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def asset_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    asset_name = query.data.split(":", 1)[1]

    signal, entry, win_rate, market_good = build_signal(asset_name)
    context.user_data["last_entry"] = entry

    if context.user_data.get(LAST_ACTION) == query.id:
        return
    context.user_data[LAST_ACTION] = query.id

    await query.edit_message_text(
        text=signal,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("ربحت الصفقة 😍🔥🔥", callback_data="win"),
             InlineKeyboardButton("لقد خسرت الصفقة 😔", callback_data="lose")]
        ])
    )

async def handle_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    entry = context.user_data.get("last_entry", 10)

    if context.user_data.get(LAST_ACTION) == query.id:
        return
    context.user_data[LAST_ACTION] = query.id

    if query.data == "win":
        context.user_data[WINS] += 1
        profit = round(entry * 0.8, 2)
        context.user_data[BALANCE] += profit
        context.user_data[PROFIT] += profit
        msg = (f"ربحت الصفقة! 🎉\n"
               f"الربح من هذه الصفقة: {profit} ريال\n"
               f"رصيدك الآن: {context.user_data[BALANCE]:.2f} ريال\n"
               f"عدد الصفقات الرابحة: {context.user_data[WINS]}\n"
               f"عدد الصفقات الخاسرة: {context.user_data[LOSSES]}\n"
               f"إجمالي الربح: {context.user_data[PROFIT]:.2f} ريال")
    else:
        context.user_data[LOSSES] += 1
        context.user_data[BALANCE] -= entry
        context.user_data[PROFIT] -= entry
        msg = (f"لقد خسرت الصفقة 😔\n"
               f"خسرت: {entry} ريال\n"
               f"رصيدك الآن: {context.user_data[BALANCE]:.2f} ريال\n"
               f"عدد الصفقات الرابحة: {context.user_data[WINS]}\n"
               f"عدد الصفقات الخاسرة: {context.user_data[LOSSES]}\n"
               f"إجمالي الربح: {context.user_data[PROFIT]:.2f} ريال")
    await query.edit_message_text(msg)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (f"رصيدك: {context.user_data.get(BALANCE, 0):.2f} ريال\n"
           f"عدد الصفقات الرابحة: {context.user_data.get(WINS, 0)}\n"
           f"عدد الصفقات الخاسرة: {context.user_data.get(LOSSES, 0)}\n"
           f"إجمالي الربح: {context.user_data.get(PROFIT, 0):.2f} ريال")
    await update.message.reply_text(msg)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_balance)],
            TRADING: [CommandHandler("signal", send_signal)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(asset_signal, pattern=r"^asset:"))
    app.add_handler(CallbackQueryHandler(handle_result, pattern="^(win|lose)$"))
    app.add_handler(CommandHandler("stats", stats))
    app.run_polling()
