import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config import BOT_TOKEN, BOT_MODE, WEBHOOK_PATH, WEBHOOK_URL, PORT, HOST
from handlers.handlers import register_handlers
from handlers.admin import register_admin_handlers
from utils.cleanup import cleanup_temp_directory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print(f"===== Application Startup at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} =====\n")


class VidZillaBot:

    def __init__(self):
        self.bot = None
        self.dp = None
        self.runner = None
        self.mode = (BOT_MODE or "polling").lower().strip()
        if self.mode not in {"webhook", "polling"}:
            logger.warning("Unknown BOT_MODE=%s. Falling back to 'polling'.", self.mode)
            self.mode = "polling"

    async def _setup(self):
        cleanup_temp_directory()
        self.bot = Bot(token=BOT_TOKEN)
        self.dp = Dispatcher()
        register_handlers(self.dp)
        register_admin_handlers(self.dp)
        logger.info("All handlers registered")

    async def _start_health_server(self):
        async def handle_root(request):
            return web.Response(text="Vidzilla Bot is running OK")
        app = web.Application()
        app.router.add_get("/", handle_root)
        app.router.add_get("/health", handle_root)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, HOST, PORT)
        await site.start()
        logger.info(f"Health check server started on {HOST}:{PORT}")
        return runner

    async def _run_polling(self):
        await self._setup()
        health_runner = await self._start_health_server()
        logger.info("Polling mode: deleting existing webhook")
        await self.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting long polling")
        try:
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types()
            )
        finally:
            try:
                await health_runner.cleanup()
            except Exception:
                pass

    async def _run_webhook(self):
        if not WEBHOOK_PATH or not WEBHOOK_URL:
            raise ValueError("WEBHOOK_PATH and WEBHOOK_URL are required when BOT_MODE=webhook")
        await self._setup()

        app = web.Application()
        app["bot"] = self.bot

        webhook_handler = SimpleRequestHandler(dispatcher=self.dp, bot=self.bot)
        webhook_handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, self.dp, bot=self.bot)

        app.router.add_get("/", lambda r: web.Response(text="Vidzilla Bot is running OK"))
        app.router.add_get("/health", lambda r: web.Response(text="OK"))

        async def on_startup(application):
            webhook_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
            logger.info(f"Setting webhook to {webhook_url}")
            await self.bot.set_webhook(webhook_url)

        async def on_shutdown(application):
            try:
                await self.bot.session.close()
            except Exception:
                pass

        app.on_startup.append(on_startup)
        app.on_shutdown.append(on_shutdown)

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, HOST, PORT)
        await site.start()
        logger.info(f"Web application started on {HOST}:{PORT}")
        logger.info("Vidzilla Bot started successfully!")
        await asyncio.Event().wait()

    async def run(self):
        try:
            if self.mode == "polling":
                await self._run_polling()
            else:
                await self._run_webhook()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            if self.runner:
                try:
                    await self.runner.cleanup()
                except Exception:
                    pass
            if self.bot:
                try:
                    await self.bot.session.close()
                except Exception:
                    pass
            logger.info("Cleanup complete")


async def main():
    logger.info("Starting Vidzilla Bot - FREE Version in %s mode", (BOT_MODE or "polling"))
    await VidZillaBot().run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated")
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        exit(1)
