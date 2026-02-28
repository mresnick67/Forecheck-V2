import asyncio
import logging

import app.models  # noqa: F401
from app.config import get_settings
from app.database import Base, engine
from app.migrations import ensure_schema_updates
from app.services.nhl_sync import run_periodic_sync


logger = logging.getLogger(__name__)
settings = get_settings()


async def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_updates(engine)

    if not settings.nhl_sync_enabled:
        logger.info("NHL sync disabled. Worker exiting.")
        return
    logger.info("Starting sync worker loop.")
    await run_periodic_sync()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
