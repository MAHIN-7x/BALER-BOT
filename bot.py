import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

import database as db
from handlers import router

TOKEN = os.getenv("BOT_TOKEN", "8804237291:AAGC5a-3etKqlpEbLU0Hvp_yCUWmXi5dNRY")
PORT  = int(os.getenv("PORT", 8080))


async def handle_ping(request):
    return web.Response(text="Bot is alive!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info("Web server running on port %s", PORT)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    await db.init_db()

    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )
    dp = Dispatcher()
    dp.include_router(router)

    await start_web_server()

    logging.info("Bot is starting...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
