"""Lightweight migrations for production safety."""

from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def ensure_user_yahoo_columns(engine: Engine) -> None:
    """Ensure Yahoo OAuth columns exist on users table."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    missing = [
        ("yahoo_access_token", "TEXT"),
        ("yahoo_refresh_token", "TEXT"),
        ("yahoo_token_expires_at", "TIMESTAMP"),
        ("yahoo_user_guid", "VARCHAR(100)"),
    ]

    with engine.begin() as connection:
        for name, sql_type in missing:
            if name in existing:
                continue
            logger.info("Adding missing column users.%s", name)
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))


def ensure_user_auth_columns(engine: Engine) -> None:
    """Ensure auth refresh token columns exist on users table."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    missing = [
        ("refresh_token_hash", "TEXT"),
        ("refresh_token_expires_at", "TIMESTAMP"),
        ("refresh_token_last_used_at", "TIMESTAMP"),
    ]

    with engine.begin() as connection:
        for name, sql_type in missing:
            if name in existing:
                continue
            logger.info("Adding missing column users.%s", name)
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))


def ensure_schema_updates(engine: Engine) -> None:
    ensure_user_yahoo_columns(engine)
    ensure_user_auth_columns(engine)
    _ensure_app_settings_table(engine)
    _ensure_scan_alert_tables(engine)
    _ensure_game_columns(engine)
    _ensure_player_game_stats_columns(engine)
    _ensure_player_rolling_stats_columns(engine)
    _ensure_scan_columns(engine)
    _ensure_scan_rule_columns(engine)
    _ensure_scan_preferences_table(engine)
    _ensure_team_week_schedule_table(engine)
    _ensure_sync_state_timezone(engine)
    _ensure_indexes(engine)
    _backfill_scope_columns(engine)


def _ensure_app_settings_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if "app_settings" in inspector.get_table_names():
        return

    with engine.begin() as connection:
        logger.info("Creating app_settings table")
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS app_settings ("
            "key TEXT PRIMARY KEY,"
            "value_json TEXT NOT NULL,"
            "updated_at TIMESTAMP"
            ")"
        ))


def _ensure_scan_alert_tables(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "scan_runs" not in tables:
            logger.info("Creating scan_runs table")
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS scan_runs ("
                "id VARCHAR(36) PRIMARY KEY,"
                "scan_id VARCHAR(36) NOT NULL,"
                "run_at TIMESTAMP,"
                "match_count INTEGER DEFAULT 0,"
                "error VARCHAR(500)"
                ")"
            ))
        if "scan_alert_state" not in tables:
            logger.info("Creating scan_alert_state table")
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS scan_alert_state ("
                "id VARCHAR(36) PRIMARY KEY,"
                "scan_id VARCHAR(36) NOT NULL,"
                "player_id VARCHAR(36) NOT NULL,"
                "is_current_match BOOLEAN DEFAULT 0,"
                "last_matched_at TIMESTAMP,"
                "last_notified_at TIMESTAMP,"
                "created_at TIMESTAMP,"
                "updated_at TIMESTAMP"
                ")"
            ))


def _ensure_game_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "games" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("games")}
    columns = [
        ("season_id", "VARCHAR(8)"),
        ("game_type", "INTEGER"),
        ("start_time_utc", "TIMESTAMP"),
        ("end_time_utc", "TIMESTAMP"),
        ("status_source", "VARCHAR(20)"),
    ]

    with engine.begin() as connection:
        for name, sql_type in columns:
            if name in existing:
                continue
            logger.info("Adding missing column games.%s", name)
            connection.execute(text(f"ALTER TABLE games ADD COLUMN {name} {sql_type}"))


def _ensure_player_game_stats_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "player_game_stats" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("player_game_stats")}
    columns = [
        ("season_id", "VARCHAR(8)"),
        ("game_type", "INTEGER"),
        ("team_abbrev", "VARCHAR(10)"),
        ("opponent_abbrev", "VARCHAR(10)"),
        ("is_home", "BOOLEAN"),
        ("takeaways", "INTEGER"),
        ("giveaways", "INTEGER"),
        ("save_percentage", "FLOAT"),
        ("goalie_decision", "VARCHAR(2)"),
        ("goalie_starter", "BOOLEAN"),
        ("even_strength_shots_against", "INTEGER"),
        ("power_play_shots_against", "INTEGER"),
        ("shorthanded_shots_against", "INTEGER"),
        ("even_strength_goals_against", "INTEGER"),
        ("power_play_goals_against", "INTEGER"),
        ("shorthanded_goals_against", "INTEGER"),
    ]

    with engine.begin() as connection:
        for name, sql_type in columns:
            if name in existing:
                continue
            logger.info("Adding missing column player_game_stats.%s", name)
            connection.execute(text(f"ALTER TABLE player_game_stats ADD COLUMN {name} {sql_type}"))


def _ensure_player_rolling_stats_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "player_rolling_stats" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("player_rolling_stats")}
    columns = [
        ("season_id", "VARCHAR(8)"),
        ("game_type", "INTEGER"),
        ("window_size", "INTEGER"),
        ("last_game_date", "TIMESTAMP"),
        ("total_saves", "INTEGER"),
        ("total_shots_against", "INTEGER"),
        ("total_goals_against", "INTEGER"),
        ("goalie_games_started", "INTEGER"),
        ("temperature_tag", "VARCHAR(10)"),
    ]

    with engine.begin() as connection:
        for name, sql_type in columns:
            if name in existing:
                continue
            logger.info("Adding missing column player_rolling_stats.%s", name)
            connection.execute(text(f"ALTER TABLE player_rolling_stats ADD COLUMN {name} {sql_type}"))


def _ensure_scan_rule_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "scan_rules" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("scan_rules")}
    columns = [
        ("compare_window", "VARCHAR(10)"),
    ]

    with engine.begin() as connection:
        for name, sql_type in columns:
            if name in existing:
                continue
            logger.info("Adding missing column scan_rules.%s", name)
            connection.execute(text(f"ALTER TABLE scan_rules ADD COLUMN {name} {sql_type}"))


def _ensure_scan_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "scans" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("scans")}
    columns = [
        ("position_filter", "VARCHAR(5)"),
    ]

    with engine.begin() as connection:
        for name, sql_type in columns:
            if name in existing:
                continue
            logger.info("Adding missing column scans.%s", name)
            connection.execute(text(f"ALTER TABLE scans ADD COLUMN {name} {sql_type}"))


def _ensure_scan_preferences_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if "scan_preferences" in inspector.get_table_names():
        return

    with engine.begin() as connection:
        logger.info("Creating scan_preferences table")
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS scan_preferences ("
            "id VARCHAR(36) PRIMARY KEY,"
            "user_id VARCHAR(36) NOT NULL,"
            "scan_id VARCHAR(36) NOT NULL,"
            "is_hidden BOOLEAN DEFAULT 0,"
            "is_followed BOOLEAN DEFAULT 0,"
            "alerts_enabled BOOLEAN DEFAULT 0,"
            "created_at TIMESTAMP,"
            "updated_at TIMESTAMP"
            ")"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_scan_preferences_user_scan "
            "ON scan_preferences (user_id, scan_id)"
        ))


def _ensure_team_week_schedule_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if "team_week_schedules" in inspector.get_table_names():
        return

    with engine.begin() as connection:
        logger.info("Creating team_week_schedules table")
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS team_week_schedules ("
            "id VARCHAR(36) PRIMARY KEY,"
            "team_abbrev VARCHAR(10) NOT NULL,"
            "season_id VARCHAR(8) NOT NULL,"
            "week_start DATE NOT NULL,"
            "week_end DATE NOT NULL,"
            "games_total INTEGER DEFAULT 0,"
            "light_games INTEGER DEFAULT 0,"
            "heavy_games INTEGER DEFAULT 0,"
            "updated_at TIMESTAMP"
            ")"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_team_week_schedule "
            "ON team_week_schedules (team_abbrev, season_id, week_start)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_team_week_schedule_week "
            "ON team_week_schedules (week_start, season_id)"
        ))


def _ensure_sync_state_timezone(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    if "sync_state" not in inspector.get_table_names():
        return

    columns = {col["name"]: col for col in inspector.get_columns("sync_state")}
    last_run = columns.get("last_run_at")
    if last_run is None:
        return

    col_type = str(last_run.get("type", "")).lower()
    if "timestamp" in col_type and "with time zone" in col_type:
        return

    with engine.begin() as connection:
        logger.info("Converting sync_state.last_run_at to timestamptz (UTC)")
        connection.execute(text(
            "ALTER TABLE sync_state "
            "ALTER COLUMN last_run_at TYPE TIMESTAMPTZ "
            "USING last_run_at AT TIME ZONE 'UTC'"
        ))


def _ensure_indexes(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "player_game_stats" in tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_player_game_stats_player_game "
                "ON player_game_stats (player_id, game_id)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_player_game_stats_player_date "
                "ON player_game_stats (player_id, date)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_player_game_stats_season_game_type_date "
                "ON player_game_stats (season_id, game_type, date)"
            ))
        if "player_rolling_stats" in tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_player_rolling_stats_scope "
                "ON player_rolling_stats (player_id, \"window\", season_id, game_type)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_player_rolling_stats_window_scope "
                "ON player_rolling_stats (\"window\", season_id, game_type)"
            ))
        if "games" in tables:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_games_season_game_type_date "
                "ON games (season_id, game_type, date)"
            ))
        if "player_ownership_snapshots" in tables:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_ownership_snapshots_player_date "
                "ON player_ownership_snapshots (player_id, as_of)"
            ))
        if "scan_runs" in tables:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_scan_runs_scan_run_at "
                "ON scan_runs (scan_id, run_at)"
            ))
        if "scan_alert_state" in tables:
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_scan_alert_state_scan_player "
                "ON scan_alert_state (scan_id, player_id)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_scan_alert_state_notified "
                "ON scan_alert_state (scan_id, is_current_match, last_notified_at)"
            ))


def _backfill_scope_columns(engine: Engine) -> None:
    from app.services.season import season_id_for_date, current_game_type, current_season_id

    def _parse_datetime(value) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "games" in tables:
            rows = connection.execute(
                text("SELECT id, date FROM games WHERE season_id IS NULL")
            ).fetchall()
            for row in rows:
                game_date = _parse_datetime(row.date)
                season_id = season_id_for_date(game_date) if game_date else current_season_id()
                connection.execute(
                    text("UPDATE games SET season_id = :season_id WHERE id = :id"),
                    {"season_id": season_id, "id": row.id},
                )

            connection.execute(
                text("UPDATE games SET game_type = :game_type WHERE game_type IS NULL"),
                {"game_type": current_game_type()},
            )

        if "player_game_stats" in tables:
            stats_rows = connection.execute(
                text("SELECT id, date FROM player_game_stats WHERE season_id IS NULL")
            ).fetchall()
            for row in stats_rows:
                stats_date = _parse_datetime(row.date)
                season_id = season_id_for_date(stats_date) if stats_date else current_season_id()
                connection.execute(
                    text("UPDATE player_game_stats SET season_id = :season_id WHERE id = :id"),
                    {"season_id": season_id, "id": row.id},
                )

            connection.execute(
                text("UPDATE player_game_stats SET game_type = :game_type WHERE game_type IS NULL"),
                {"game_type": current_game_type()},
            )

        if "player_rolling_stats" in tables:
            rolling_rows = connection.execute(
                text("SELECT id, \"window\" FROM player_rolling_stats WHERE season_id IS NULL")
            ).fetchall()
            for row in rolling_rows:
                season_id = current_season_id()
                window_size = _window_size_from_label(row.window)
                connection.execute(
                    text(
                        "UPDATE player_rolling_stats "
                        "SET season_id = :season_id, game_type = :game_type, window_size = :window_size "
                        "WHERE id = :id"
                    ),
                    {
                        "season_id": season_id,
                        "game_type": current_game_type(),
                        "window_size": window_size,
                        "id": row.id,
                    },
                )

            connection.execute(
                text("UPDATE player_rolling_stats SET game_type = :game_type WHERE game_type IS NULL"),
                {"game_type": current_game_type()},
            )


def _window_size_from_label(label: str | None) -> int | None:
    if not label:
        return None
    label = label.strip().upper()
    if label == "L5":
        return 5
    if label == "L10":
        return 10
    if label == "L20":
        return 20
    return None
