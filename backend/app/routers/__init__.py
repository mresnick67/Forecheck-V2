from app.routers.auth import router as auth_router
from app.routers.players import router as players_router
from app.routers.scans import router as scans_router
from app.routers.leagues import router as leagues_router
from app.routers.admin import router as admin_router
from app.routers.yahoo_auth import router as yahoo_auth_router
from app.routers.schedule import router as schedule_router
from app.routers.setup import router as setup_router

__all__ = [
    "auth_router",
    "players_router",
    "scans_router",
    "leagues_router",
    "admin_router",
    "yahoo_auth_router",
    "schedule_router",
    "setup_router",
]
