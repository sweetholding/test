import aiohttp
import asyncio
import time
import json
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

wallet_limits = {
    "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": ("binance", 100000),
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2": ("bybit", 100000),
    "FpwQQhQQoEaVu3WU2qZMfF1hx48YyfwsLoRgXG83E99Q": ("coinbace", 100000),
    "ASTyfSima4LLAdDgoFGkgqoKowG1LZFDr9fAQrg7iaJZ": ("mex", 100000),
    "FxteHmLwG9nk1eL4pjNve3Eub2goGkkz6g6TbvdmW46a": ("bitfinex", 100000),
    "FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5": ("kraken", 100000),
    "BmFdpraQhkiDQE6SnfG5omcA1VwzqfXrwtNYBwWTymy6": ("cukoin", 100000),
    "C68a6RCGLiPskbPYtAcsCjhG8tfTWYcoB4JjCrXFdqyo": ("okx", 100000),
}

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
        if isinstance(data, list):
            data = data[0]

        sol_price = await get_cached_sol_price()
        signature = data.get("signature", "-")
        transfers = data.get("tokenTransfers", [])
        account_data = data.get("accountData", [])

        symbol = "SPL"
        mint = "-"
        sender = "-"
        receiver = "-"
        usd_amount = 0

        if transfers:
            for tr in transfers:
                mint = tr.get("mint", "-")
                symbol = tr.get("tokenSymbol", "SPL")
                sender = tr.get("fromUserAccount", "-")
                receiver = tr.get("toUserAccount", "-")
                break

        elif account_data:
            for entry in account_data:
                native_change = entry.get("nativeBalanceChange", 0)
                amount_sol = native_change / 1_000_000_000
                usd_amount = abs(amount_sol * sol_price)
                sender = entry.get("account", "-")
                symbol = "SOL"
                break

        if usd_amount == 0:
            amount_raw = data.get("events", {}).get("nativeTransfer", {}).get("amount", 0)
            usd_amount = abs(amount_raw / 1_000_000_000 * sol_price)

        involved_wallet = None
        for address in [sender, receiver]:
            if address in wallet_limits:
                involved_wallet = address
                break

        if not involved_wallet:
            return

        name, limit = wallet_limits[involved_wallet]
        if usd_amount < limit:
            return

        arrow = "⬅️ withdraw from" if receiver not in wallet_limits else "➡️ deposit to"

        msg = (
            f"🔍 {symbol} on Solana\n"
            f"💰 {usd_amount:,.0f}$\n"
            f"👇 `{sender}`\n"
            f"👆 `{receiver}`\n"
            f"📊 {arrow} ({name})\n"
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
    await app.start()

    web_app = web.Application()
    web_app["application"] = app
    web_app["bot_loop"] = asyncio.get_event_loop()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_post(webhook_path, app.webhook_handler())

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, port=8000)
    await site.start()

    print("🟢 Сервер запущен на порту 8000")
    await notify_users("✅ Бот запущен и работает на Render.", app)

    while True:
        await asyncio.sleep(3600)

def main():
    global app
    app = ApplicationBuilder().token(TOKEN).build()
    asyncio.run(start_bot())

if __name__ == "__main__":
    main()
