import aiohttp
import asyncio
import time
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "7701492175:AAHvAskxHi2asdQ3iVYohFFrGAM8s3OcrGk"
ADMIN_ID = 423798633
GROUP_CHAT_ID = -1002540099411
USERS_FILE = "users.txt"
HELIUS_API_KEY = "8f1ab601-c0db-4aec-aa03-578c8f5a52fa"

sol_price_cache = {"price": None, "last_updated": 0}

STABLECOINS = {"USDC", "USDT", "USDH", "UXD", "DAI", "USDP", "TUSD", "FRAX"}
STABLECOIN_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERCLztnttdr5YwUXrjbsLkxkMtFvY7kKfM",
    "7kbnvuGBxxj8AG9qp8Scn56muWGaRaFqxg1FsRp3PaFT",
    "E8u5Vp3xwPRdRzxrBrPLowGEXRJnLUxbJMc1oFn4nqEa",
    "FZ8d3D8gaEj1eLNYsZTcq7Nh8hhCXi2GsN5D9YXcRJ8L",
    "EaWXmTJEo9u3sxVcqBFVyUVJ7BQ3tj56b2dcHzURkNfG",
    "2QYdQ2Tz2wmu9Xc9e1KD1TV6koEbnKRTvnrpK21FyuTL",
    "FR87nWEUxVgerFGhZM8Y4AggKGLnaXswr1Pd8wZ4kZcp",
}

wallet_limits = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": ("binance", 100000),
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2": ("bybit", 100000),
    "FpwQQhQQoEaVu3WU2qZMfF1hx48YyfwsLoRgXG83E99Q": ("coinbase", 100000),
    "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ": ("mex", 100000),
    "FxteHmLwG9nk1eL4pjNve3Eub2goGkkz6g6TbvdmW46a": ("bitfinex", 100000),
    "FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5": ("kraken", 100000),
    "BmFdpraQhkiDQE6SnfG5omcA1VwzqfXrwtNYBwWTymy6": ("kucoin", 100000),
    "C68a6RCGLiPskbPYtAcsCjhG8tfTWYcoB4JjCrXFdqyo": ("okx", 100000),
    "9fFcDYoyqVpdpTSF1Mu7EyTMBpDZ75m3zBXCxVZD8pjt": ("me", 1),
}

app = ApplicationBuilder().token(TOKEN).build()

async def get_cached_sol_price():
    now = time.time()
    if sol_price_cache["price"] and (now - sol_price_cache["last_updated"] < 3600):
        return sol_price_cache["price"]
    url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                price = data["solana"]["usd"]
                sol_price_cache["price"] = price
                sol_price_cache["last_updated"] = now
                return price
    except:
        return sol_price_cache["price"] or 0

async def notify_users(msg, application):
    try:
        await application.bot.send_message(chat_id=GROUP_CHAT_ID, text=msg, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ Ошибка отправки в группу: {e}")
    try:
        with open(USERS_FILE, "r") as f:
            user_ids = [int(line.strip()) for line in f if line.strip()]
    except:
        user_ids = []
    for uid in user_ids:
        try:
            await application.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Ошибка отправки пользователю {uid}: {e}")

async def handle_transfer(data, application):
    try:
        if isinstance(data, dict):
            data = [data]

        sol_price = await get_cached_sol_price()

        for tx in data:
            signature = tx.get("signature", "-")
            transfers = tx.get("tokenTransfers", [])

            for tr in transfers:
                if not isinstance(tr, dict):
                    continue

                mint = tr.get("mint", "-")
                symbol = tr.get("tokenSymbol", "SPL")
                sender = tr.get("fromUserAccount", "-")
                receiver = tr.get("toUserAccount", "-")

                if symbol.upper() in STABLECOINS or mint in STABLECOIN_MINTS:
                    continue

                native_input = tr.get("nativeInput")
                if not isinstance(native_input, dict):
                    continue

                lamports = native_input.get("amount")
                if not isinstance(lamports, (int, float)):
                    continue

                sol_spent = lamports / 1_000_000_000
                usd_amount = sol_spent * sol_price

                direction = None
                if sender in wallet_limits:
                    if usd_amount < wallet_limits[sender][1]:
                        continue
                    direction = f"📤 withdraw from ({wallet_limits[sender][0]})"
                elif receiver in wallet_limits:
                    if usd_amount < wallet_limits[receiver][1]:
                        continue
                    direction = f"📥 deposit to ({wallet_limits[receiver][0]})"
                else:
                    continue

                msg = (
                    f"{symbol} on Solana\n"
                    f"💰 {usd_amount:,.2f}$\n"
                    f"📤 `{sender}`\n"
                    f"📥 `{receiver}`\n"
                    f"📊 {direction}\n"
                    f"🔗 https://solscan.io/tx/{signature}"
                )
                await notify_users(msg, application)

    except Exception as e:
        print(f"[handle_transfer error] {e}")

async def webhook_handler(request):
    print("📥 Webhook получен")
    try:
        data = await request.json()
        request.app["bot_loop"].create_task(handle_transfer(data, request.app["application"]))
    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")
    return web.Response(text="OK")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        await update.message.reply_text("⛔ Только админ может использовать этого бота.")
        return
    with open(USERS_FILE, "a+") as f:
        f.seek(0)
        if str(uid) not in f.read():
            f.write(f"{uid}\n")
    await update.message.reply_text("✅ Подписка активна.")

async def start_bot():
    app.add_handler(CommandHandler("start", start))
    webhook_path = "/telegram"
    webhook_url = f"https://test-dvla.onrender.com{webhook_path}"
    await app.initialize()
    await app.bot.set_webhook(webhook_url)
    print(f"📡 Webhook установлен: {webhook_url}")
    await app.start()
    web_app = web.Application()
    web_app["application"] = app
    web_app["bot_loop"] = asyncio.get_event_loop()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_post(webhook_path, webhook_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, port=port)
    await site.start()
    print("🟢 Сервер запущен")
    await notify_users("✅ Бот запущен и работает на Render.", app)
    while True:
        await asyncio.sleep(3600)

def main():
    asyncio.run(start_bot())

if __name__ == "__main__":
    main()
