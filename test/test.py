import aiohttp
import asyncio
import time
import json
import logging
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "7701492175:AAHvAskxHi2asdQ3iVYohFFrGAM8s3OcrGk"
ADMIN_ID = 423798633
USERS_FILE = "users.txt"
WALLETS_FILE = "wallets.json"
HELIUS_API_KEY = "8f1ab601-c0db-4aec-aa03-578c8f5a52fa"
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
STABLECOINS = {"USDC", "USDT", "USDH", "UXD", "DAI", "USDP", "TUSD", "FRAX"}

sol_price_cache = {"price": None, "last_updated": 0}
wallet_limits = {}

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
        with open(USERS_FILE, "r") as f:
            user_ids = [int(line.strip()) for line in f if line.strip()]
    except:
        user_ids = []
    for uid in user_ids:
        try:
            await application.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            print(f"✅ Отправлено пользователю {uid}")
        except Exception as e:
            print(f"❌ Ошибка отправки пользователю {uid}: {e}")

async def handle_transfer(data, application):
    try:
        if isinstance(data, list):
            data = data[0]

        sol_price = await get_cached_sol_price()
        signature = data.get("signature", "-")
        account_data = data.get("accountData", [])
        for entry in account_data:
            sender = entry.get("account", "")
            native_change = entry.get("nativeBalanceChange", 0)
            amount_sol = native_change / 1_000_000_000
            amount_usd = amount_sol * sol_price
            if abs(amount_usd) < 1:
                continue
            label = "-"
            symbol = "SOL"
            mint = "-"
            receiver = "-"
            msg = (
                f"⚠️ *Новая транзакция в Solana*\n"
                f"📊Биржа: *{label}*\n"
                f"🎯Токен: `{symbol}`\n"
                f"📟Адрес токена: `{mint}`\n"
                f"🔁От: `{sender}`\n"
                f"➡️Кому: `{receiver}`\n"
                f"💰Сумма: ${amount_usd:,.2f} (≈ {amount_sol:.4f} SOL)\n"
                f"🔗 [Посмотреть в Solscan](https://solscan.io/tx/{signature})"
            )
            await notify_users(msg, application)
            break
    except Exception as e:
        print(f"[handle_transfer error] {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        with open(USERS_FILE, "a+") as f:
            f.seek(0)
            if str(uid) not in f.read():
                f.write(f"{uid}\n")
        await update.message.reply_text("✅ Подписка активна.")
    except:
        pass

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        with open(USERS_FILE, "r") as f:
            users = f.read()
        await update.message.reply_text(f"👥 Подписчики:\n{users}")
    except:
        pass

async def deluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 1:
        return await update.message.reply_text("Формат: /deluser ID")
    uid = context.args[0]
    try:
        with open(USERS_FILE, "r") as f:
            lines = f.readlines()
        with open(USERS_FILE, "w") as f:
            for line in lines:
                if line.strip() != uid:
                    f.write(line)
        await update.message.reply_text(f"Удалено: {uid}")
    except:
        pass

async def add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        return await update.message.reply_text("Формат: /addwallet адрес лимит")
    wallet, limit = context.args
    try:
        with open(WALLETS_FILE, "r") as f:
            wallets = json.load(f)
    except:
        wallets = {}
    wallets[wallet] = float(limit)
    with open(WALLETS_FILE, "w") as f:
        json.dump(wallets, f)
    await update.message.reply_text(f"✅ Добавлен: {wallet} с лимитом {limit} USD")

async def del_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        return await update.message.reply_text("Формат: /delwallet адрес")
    wallet = context.args[0]
    try:
        with open(WALLETS_FILE, "r") as f:
            wallets = json.load(f)
        if wallet in wallets:
            del wallets[wallet]
            with open(WALLETS_FILE, "w") as f:
                json.dump(wallets, f)
            await update.message.reply_text(f"🗑️ Удалён: {wallet}")
        else:
            await update.message.reply_text("Не найден.")
    except:
        await update.message.reply_text("Ошибка при удалении.")

async def list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(WALLETS_FILE, "r") as f:
            wallets = json.load(f)
        msg = "📋 Список кошельков:\n" + "\n".join(f"{k} — ${v}" for k, v in wallets.items())
        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("Кошельки не найдены.")

async def set_dex_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Формат: /setdexlimit пока не реализован.")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Режим отладки активирован.")

async def pause_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏸️ Бот приостановлен.")

async def resume_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("▶️ Бот возобновлён.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ Бот остановлен.")

async def webhook_handler(request):
    print("📥 Webhook получен")
    try:
        data = await request.json()
        print(json.dumps(data, indent=2))
        request.app["bot_loop"].create_task(handle_transfer(data, request.app["application"]))
    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")
    return web.Response(text="OK")

async def create_webhook_handler(request):
    origin = str(request.url).split("/")[2]
    webhook_url = f"https://{origin}/webhook"
    payload = {
        "webhookURL": webhook_url,
        "transactionTypes": ["TRANSFER"],
        "webhookType": "enhanced",
        "accountAddresses": [],
        "authHeader": AUTH_TOKEN
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://api.helius.xyz/v0/webhooks?api-key={HELIUS_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as resp:
            result = await resp.json()
            print("✅ Webhook создан:", result)
            return web.json_response(result)

async def start_bot():
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("deluser", deluser))
    app.add_handler(CommandHandler("addwallet", add_wallet))
    app.add_handler(CommandHandler("delwallet", del_wallet))
    app.add_handler(CommandHandler("wallets", list_wallets))
    app.add_handler(CommandHandler("setdexlimit", set_dex_limit))
    app.add_handler(CommandHandler("debug", debug))
    app.add_handler(CommandHandler("pausebot", pause_bot))
    app.add_handler(CommandHandler("resumebot", resume_bot))
    app.add_handler(CommandHandler("stop", stop))

    webhook_path = "/telegram"
    webhook_url = f"https://test-dvla.onrender.com{webhook_path}"

    await app.initialize()
    await app.bot.set_webhook(webhook_url)
    await app.start()

    web_app = web.Application()
    web_app["application"] = app
    web_app["bot_loop"] = asyncio.get_event_loop()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_post("/create-webhook", create_webhook_handler)
    web_app.router.add_post(webhook_path, app.webhook_handler())  # 📌 Добавляем обработчик Telegram

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, port=8000)
    await site.start()
    print("🟢 Сервер запущен на порту 8000")

    await notify_users("✅ Бот запущен и работает на Render.", app)

def main():
    global app
    app = ApplicationBuilder().token(TOKEN).build()
    asyncio.run(start_bot())

if __name__ == "__main__":
    main()
