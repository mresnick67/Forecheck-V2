import asyncio
import logging

from app.config import get_settings
from app.services.nhl_sync import run_periodic_sync


logger = logging.getLogger(__name__)
settings = get_settings()


async def main() -> None:
    if not settings.nhl_sync_enabled:
        logger.info("NHL sync disabled. Worker exiting.")
        return
    logger.info("Starting sync worker loop.")
    await run_periodic_sync()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
