"""
NHL Stats API client for fetching detailed player statistics.

Uses the api.nhle.com/stats/rest endpoints which provide more complete data
than the api-web.nhle.com endpoints (which lack hits, blocks, etc.)
"""

import importlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional, Any, Union
import httpx

try:
    from nhlpy import NHLClient
except Exception:  # pragma: no cover - nhlpy may be missing in some environments
    NHLClient = None

logger = logging.getLogger(__name__)

STATS_API_BASE = "https://api.nhle.com/stats/rest/en"
MAX_PAGE_SIZE = 100  # API appears to cap results at 100 per request.
MAX_STATS_OFFSET = 10000  # Stats API returns empty beyond ~10k rows per query.
DEFAULT_GAME_WINDOW_DAYS = 7


def _client() -> Optional["NHLClient"]:
    if NHLClient is None:
        return None
    return NHLClient()


def _get_nhlpy_attr(name: str) -> Optional[object]:
    try:
        nhlpy = importlib.import_module("nhlpy")
    except Exception:
        return None
    return getattr(nhlpy, name, None)


def _add_query(builder: object, query: object) -> None:
    if query is None:
        return
    for method_name in ("add_query", "add_filter", "add"):
        method = getattr(builder, method_name, None)
        if callable(method):
            method(query)
            return
    queries = getattr(builder, "queries", None)
    if isinstance(queries, list):
        queries.append(query)


def _build_query_context(
    season_id: str,
    game_type: Optional[int],
    player_id: Optional[str] = None,
    start: Optional[int] = None,
    limit: Optional[int] = None,
) -> Optional[object]:
    query_builder_cls = _get_nhlpy_attr("QueryBuilder")
    if query_builder_cls is None:
        return None

    builder = query_builder_cls()
    season_query_cls = _get_nhlpy_attr("SeasonQuery")
    game_type_query_cls = _get_nhlpy_attr("GameTypeQuery")
    player_query_cls = _get_nhlpy_attr("PlayerIdQuery") or _get_nhlpy_attr("PlayerQuery")

    if season_query_cls is not None:
        for kwargs in (
            {"season_start": season_id, "season_end": season_id},
            {"season_id": season_id},
            {"season": season_id},
        ):
            try:
                _add_query(builder, season_query_cls(**kwargs))
                break
            except Exception:
                continue

    if game_type_query_cls is not None and game_type is not None:
        for kwargs in (
            {"game_type": game_type},
            {"game_type_id": game_type},
            {"gameTypeId": game_type},
        ):
            try:
                _add_query(builder, game_type_query_cls(**kwargs))
                break
            except Exception:
                continue

    if player_query_cls is not None and player_id is not None:
        for kwargs in (
            {"player_id": player_id},
            {"playerId": player_id},
            {"id": player_id},
        ):
            try:
                _add_query(builder, player_query_cls(**kwargs))
                break
            except Exception:
                continue

    for setter_name, value in (("set_start", start), ("set_limit", limit)):
        if value is None:
            continue
        setter = getattr(builder, setter_name, None)
        if callable(setter):
            setter(value)

    for method_name in ("build_query_context", "get_query_context", "build"):
        method = getattr(builder, method_name, None)
        if callable(method):
            return method()

    return getattr(builder, "query_context", None)


def _nhlpy_stats_call(
    report_type: str,
    query_context: object,
    aggregate: bool,
    method_name: str,
) -> Optional[List[Dict[str, Any]]]:
    client = _client()
    if client is None:
        return None

    stats_module = getattr(client, "stats", None)
    method = getattr(stats_module, method_name, None) if stats_module else None
    if not callable(method):
        return None

    try:
        data = method(report_type, query_context, aggregate=aggregate)
    except Exception as exc:
        logger.warning("nhl-api-py stats call failed: %s", exc)
        return None

    if isinstance(data, dict):
        return data.get("data") or data.get("results") or data.get("stats")
    return data if isinstance(data, list) else None


@dataclass
class SkaterGameStats:
    """Skater per-game statistics from the NHL Stats API."""
    player_id: str
    game_id: str
    game_date: datetime
    team: str
    opponent: str
    is_home: bool
    # Scoring
    goals: int
    assists: int
    points: int
    shots: int
    plus_minus: int
    pim: int
    pp_points: int
    sh_points: int
    toi_seconds: float
    # Peripherals (from realtime endpoint)
    hits: int
    blocks: int
    takeaways: int
    giveaways: int


@dataclass
class GoalieGameStats:
    """Goalie per-game statistics from the NHL Stats API."""
    player_id: str
    game_id: str
    game_date: datetime
    team: str
    opponent: str
    is_home: bool
    saves: int
    shots_against: int
    goals_against: int
    save_pct: float
    wins: int
    losses: int
    ot_losses: int
    shutouts: int
    toi_seconds: float


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string from the API."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            cleaned = date_str.strip()
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1] + "+00:00"
            if "T" in cleaned or "+" in cleaned:
                return datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int."""
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_toi_seconds(value: Any) -> float:
    """Parse time-on-ice values to seconds."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if ":" in value:
            parts = value.split(":")
            try:
                if len(parts) == 2:
                    minutes, seconds = parts
                    return float(minutes) * 60 + float(seconds)
                if len(parts) == 3:
                    hours, minutes, seconds = parts
                    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
            except ValueError:
                return 0.0
        return _safe_float(value, default=0.0)
    return 0.0


def _fetch_stats(endpoint: str, params: Dict[str, Any]) -> List[Dict]:
    """Fetch data from the NHL Stats API."""
    url = f"{STATS_API_BASE}/{endpoint}"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
    except httpx.HTTPError as e:
        logger.error(f"NHL Stats API error for {endpoint}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching {endpoint}: {e}")
        return []


def _game_cayenne_exp(
    season_id: str,
    game_type: Optional[int],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    player_id: Optional[str] = None,
) -> str:
    parts = [f"seasonId={season_id}"]
    if game_type is not None:
        parts.append(f"gameTypeId={game_type}")
    if player_id:
        parts.append(f"playerId={player_id}")
    if start_date and end_date:
        start_value = start_date.strftime("%Y-%m-%d")
        end_value = end_date.strftime("%Y-%m-%d")
        parts.append(f"gameDate>='{start_value}'")
        parts.append(f"gameDate<='{end_value}'")
    return " and ".join(parts)


def _season_date_bounds(season_id: str) -> tuple[datetime, datetime]:
    if len(season_id) == 8 and season_id.isdigit():
        start_year = int(season_id[:4])
    else:
        start_year = datetime.now(timezone.utc).year
    start_date = datetime(start_year, 7, 1, tzinfo=timezone.utc)
    end_date = datetime.now(timezone.utc)
    return start_date, end_date


def _date_windows(
    start_date: datetime,
    end_date: datetime,
    window_days: int = DEFAULT_GAME_WINDOW_DAYS,
) -> List[tuple[datetime, datetime]]:
    windows: List[tuple[datetime, datetime]] = []
    current = start_date
    while current <= end_date:
        window_end = min(current + timedelta(days=window_days - 1), end_date)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return windows


def _build_realtime_indexes(realtime_data: List[Dict[str, Any]]) -> tuple[Dict[tuple, Dict], Dict[tuple, Dict]]:
    by_game: Dict[tuple, Dict] = {}
    by_date: Dict[tuple, Dict] = {}
    for entry in realtime_data:
        player_id = entry.get("playerId")
        if player_id is None:
            continue
        player_id_str = str(player_id)
        game_id = entry.get("gameId")
        if game_id is not None:
            by_game[(player_id_str, str(game_id))] = entry
        game_date = _normalize_game_date(entry.get("gameDate") or entry.get("gameDateUTC"))
        if game_date:
            by_date[(player_id_str, game_date)] = entry
    return by_game, by_date


def _normalize_game_date(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if "T" in cleaned:
            cleaned = cleaned.split("T")[0]
        if "Z" in cleaned:
            cleaned = cleaned.replace("Z", "")
        try:
            return datetime.fromisoformat(cleaned).date().isoformat()
        except ValueError:
            return cleaned
    return None


def fetch_skater_game_stats(
    season_id: str,
    player_id: Optional[str] = None,
    game_type: Optional[int] = None,
    limit: int = 500,
) -> List[SkaterGameStats]:
    """
    Fetch skater per-game stats from the NHL Stats API.

    Combines data from both 'summary' (scoring) and 'realtime' (peripherals) endpoints.
    """
    # Build cayenne expression for filtering
    cayenne_exp = _game_cayenne_exp(
        season_id=season_id,
        game_type=game_type,
        player_id=player_id,
    )

    base_params = {
        "isAggregate": "false",
        "isGame": "true",
        "limit": min(limit, MAX_PAGE_SIZE),
        "cayenneExp": cayenne_exp,
    }

    query_context = _build_query_context(
        season_id=season_id,
        game_type=game_type,
        player_id=player_id,
        start=0,
        limit=base_params["limit"],
    )

    # Fetch scoring stats
    logger.debug(f"Fetching skater summary stats for season {season_id}")
    summary_data = None
    if query_context is not None:
        summary_data = _nhlpy_stats_call(
            report_type="summary",
            query_context=query_context,
            aggregate=False,
            method_name="skater_stats_with_query_context",
        )
    if summary_data is None:
        summary_data = _fetch_stats("skater/summary", base_params)

    # Fetch peripheral stats (hits, blocks, etc.)
    logger.debug(f"Fetching skater realtime stats for season {season_id}")
    realtime_data = None
    if query_context is not None:
        realtime_data = _nhlpy_stats_call(
            report_type="realtime",
            query_context=query_context,
            aggregate=False,
            method_name="skater_stats_with_query_context",
        )
    if realtime_data is None:
        realtime_data = _fetch_stats("skater/realtime", base_params)

    realtime_index, realtime_by_date = _build_realtime_indexes(realtime_data)

    # Merge the data
    results: List[SkaterGameStats] = []
    for entry in summary_data:
        player_id_str = str(entry.get("playerId"))
        game_id_str = str(entry.get("gameId"))
        game_date = _parse_date(entry.get("gameDate"))

        if not game_date:
            continue

        # Get peripheral stats from realtime data
        key = (player_id_str, game_id_str)
        realtime = realtime_index.get(key, {})
        if not realtime:
            normalized_date = _normalize_game_date(entry.get("gameDate") or entry.get("gameDateUTC"))
            if normalized_date:
                realtime = realtime_by_date.get((player_id_str, normalized_date), {})

        results.append(SkaterGameStats(
            player_id=player_id_str,
            game_id=game_id_str,
            game_date=game_date,
            team=entry.get("teamAbbrev", ""),
            opponent=entry.get("opponentTeamAbbrev", ""),
            is_home=entry.get("homeRoad") == "H",
            # Scoring stats from summary
            goals=_safe_int(entry.get("goals")),
            assists=_safe_int(entry.get("assists")),
            points=_safe_int(entry.get("points")),
            shots=_safe_int(entry.get("shots")),
            plus_minus=_safe_int(entry.get("plusMinus")),
            pim=_safe_int(entry.get("penaltyMinutes") or entry.get("pim")),
            pp_points=_safe_int(entry.get("ppPoints") or entry.get("powerPlayPoints")),
            sh_points=_safe_int(entry.get("shPoints") or entry.get("shorthandedPoints")),
            toi_seconds=_parse_toi_seconds(entry.get("timeOnIce") or entry.get("timeOnIcePerGame")),
            # Peripheral stats from realtime
            hits=_safe_int(realtime.get("hits") or entry.get("hits")),
            blocks=_safe_int(
                realtime.get("blockedShots")
                or realtime.get("blocks")
                or entry.get("blockedShots")
                or entry.get("blocks")
            ),
            takeaways=_safe_int(realtime.get("takeaways") or entry.get("takeaways")),
            giveaways=_safe_int(realtime.get("giveaways") or entry.get("giveaways")),
        ))

    logger.info(f"Fetched {len(results)} skater game stats for season {season_id}")
    return results


def fetch_goalie_game_stats(
    season_id: str,
    player_id: Optional[str] = None,
    game_type: Optional[int] = None,
    limit: int = 200,
) -> List[GoalieGameStats]:
    """Fetch goalie per-game stats from the NHL Stats API."""
    cayenne_parts = [f"seasonId={season_id}"]
    if game_type is not None:
        cayenne_parts.append(f"gameTypeId={game_type}")
    if player_id:
        cayenne_parts.append(f"playerId={player_id}")
    cayenne_exp = " and ".join(cayenne_parts)

    params = {
        "isAggregate": "false",
        "isGame": "true",
        "limit": min(limit, MAX_PAGE_SIZE),
        "cayenneExp": cayenne_exp,
    }

    logger.debug(f"Fetching goalie summary stats for season {season_id}")
    query_context = _build_query_context(
        season_id=season_id,
        game_type=game_type,
        player_id=player_id,
        start=0,
        limit=params["limit"],
    )
    data = None
    if query_context is not None:
        data = _nhlpy_stats_call(
            report_type="summary",
            query_context=query_context,
            aggregate=False,
            method_name="goalie_stats_with_query_context",
        )
    if data is None:
        data = _fetch_stats("goalie/summary", params)

    results: List[GoalieGameStats] = []
    for entry in data:
        game_date = _parse_date(entry.get("gameDate"))
        if not game_date:
            continue

        results.append(GoalieGameStats(
            player_id=str(entry.get("playerId")),
            game_id=str(entry.get("gameId")),
            game_date=game_date,
            team=entry.get("teamAbbrev", ""),
            opponent=entry.get("opponentTeamAbbrev", ""),
            is_home=entry.get("homeRoad") == "H",
            saves=_safe_int(entry.get("saves")),
            shots_against=_safe_int(entry.get("shotsAgainst")),
            goals_against=_safe_int(entry.get("goalsAgainst")),
            save_pct=_safe_float(
                entry.get("savePct")
                or entry.get("savePctg")
                or entry.get("savePercentage")
            ),
            wins=_safe_int(entry.get("wins")),
            losses=_safe_int(entry.get("losses")),
            ot_losses=_safe_int(entry.get("otLosses")),
            shutouts=_safe_int(entry.get("shutouts")),
            toi_seconds=_parse_toi_seconds(entry.get("timeOnIce")),
        ))

    logger.info(f"Fetched {len(results)} goalie game stats for season {season_id}")
    return results


def _fetch_skater_game_stats_window(
    season_id: str,
    game_type: Optional[int],
    start_date: datetime,
    end_date: datetime,
) -> List[SkaterGameStats]:
    results: List[SkaterGameStats] = []
    offset = 0
    batch_size = MAX_PAGE_SIZE
    cayenne_exp = _game_cayenne_exp(
        season_id=season_id,
        game_type=game_type,
        start_date=start_date,
        end_date=end_date,
    )

    while True:
        params = {
            "isAggregate": "false",
            "isGame": "true",
            "limit": batch_size,
            "start": offset,
            "cayenneExp": cayenne_exp,
        }
        summary_data = _fetch_stats("skater/summary", params)
        if not summary_data:
            break

        realtime_data = _fetch_stats("skater/realtime", params)
        realtime_index, realtime_by_date = _build_realtime_indexes(realtime_data)

        for entry in summary_data:
            player_id_str = str(entry.get("playerId"))
            game_id_str = str(entry.get("gameId"))
            game_date = _parse_date(entry.get("gameDate"))
            if not game_date:
                continue

            realtime = realtime_index.get((player_id_str, game_id_str), {})
            if not realtime:
                normalized_date = _normalize_game_date(entry.get("gameDate") or entry.get("gameDateUTC"))
                if normalized_date:
                    realtime = realtime_by_date.get((player_id_str, normalized_date), {})

            results.append(SkaterGameStats(
                player_id=player_id_str,
                game_id=game_id_str,
                game_date=game_date,
                team=entry.get("teamAbbrev", ""),
                opponent=entry.get("opponentTeamAbbrev", ""),
                is_home=entry.get("homeRoad") == "H",
                goals=_safe_int(entry.get("goals")),
                assists=_safe_int(entry.get("assists")),
                points=_safe_int(entry.get("points")),
                shots=_safe_int(entry.get("shots")),
                plus_minus=_safe_int(entry.get("plusMinus")),
                pim=_safe_int(entry.get("penaltyMinutes") or entry.get("pim")),
                pp_points=_safe_int(entry.get("ppPoints") or entry.get("powerPlayPoints")),
                sh_points=_safe_int(entry.get("shPoints") or entry.get("shorthandedPoints")),
                toi_seconds=_parse_toi_seconds(entry.get("timeOnIce") or entry.get("timeOnIcePerGame")),
                hits=_safe_int(realtime.get("hits") or entry.get("hits")),
                blocks=_safe_int(
                    realtime.get("blockedShots")
                    or realtime.get("blocks")
                    or entry.get("blockedShots")
                    or entry.get("blocks")
                ),
                takeaways=_safe_int(realtime.get("takeaways") or entry.get("takeaways")),
                giveaways=_safe_int(realtime.get("giveaways") or entry.get("giveaways")),
            ))

        if len(summary_data) < batch_size:
            break
        offset += batch_size
        if offset >= MAX_STATS_OFFSET:
            logger.warning(
                "Skater window %s to %s hit stats API offset cap (%s).",
                start_date.date(),
                end_date.date(),
                MAX_STATS_OFFSET,
            )
            break

    return results


def _fetch_goalie_game_stats_window(
    season_id: str,
    game_type: Optional[int],
    start_date: datetime,
    end_date: datetime,
) -> List[GoalieGameStats]:
    results: List[GoalieGameStats] = []
    offset = 0
    batch_size = MAX_PAGE_SIZE
    cayenne_exp = _game_cayenne_exp(
        season_id=season_id,
        game_type=game_type,
        start_date=start_date,
        end_date=end_date,
    )

    while True:
        params = {
            "isAggregate": "false",
            "isGame": "true",
            "limit": batch_size,
            "start": offset,
            "cayenneExp": cayenne_exp,
        }
        goalie_data = _fetch_stats("goalie/summary", params)
        if not goalie_data:
            break

        for entry in goalie_data:
            game_date = _parse_date(entry.get("gameDate"))
            if not game_date:
                continue

            results.append(GoalieGameStats(
                player_id=str(entry.get("playerId")),
                game_id=str(entry.get("gameId")),
                game_date=game_date,
                team=entry.get("teamAbbrev", ""),
                opponent=entry.get("opponentTeamAbbrev", ""),
                is_home=entry.get("homeRoad") == "H",
                saves=_safe_int(entry.get("saves")),
                shots_against=_safe_int(entry.get("shotsAgainst")),
                goals_against=_safe_int(entry.get("goalsAgainst")),
                save_pct=_safe_float(
                    entry.get("savePct")
                    or entry.get("savePctg")
                    or entry.get("savePercentage")
                ),
                wins=_safe_int(entry.get("wins")),
                losses=_safe_int(entry.get("losses")),
                ot_losses=_safe_int(entry.get("otLosses")),
                shutouts=_safe_int(entry.get("shutouts")),
                toi_seconds=_parse_toi_seconds(entry.get("timeOnIce")),
            ))

        if len(goalie_data) < batch_size:
            break
        offset += batch_size
        if offset >= MAX_STATS_OFFSET:
            logger.warning(
                "Goalie window %s to %s hit stats API offset cap (%s).",
                start_date.date(),
                end_date.date(),
                MAX_STATS_OFFSET,
            )
            break

    return results


def fetch_all_game_stats(
    season_id: str,
    game_type: Optional[int] = None,
) -> tuple[List[SkaterGameStats], List[GoalieGameStats]]:
    """
    Fetch all player game stats for a season.

    Returns a tuple of (skater_stats, goalie_stats).
    """
    all_skater_stats: List[SkaterGameStats] = []
    all_goalie_stats: List[GoalieGameStats] = []

    start_date, end_date = _season_date_bounds(season_id)
    windows = _date_windows(start_date, end_date, DEFAULT_GAME_WINDOW_DAYS)
    logger.info(
        "Fetching game stats in %s date windows (%s to %s)",
        len(windows),
        start_date.date(),
        end_date.date(),
    )

    for window_start, window_end in windows:
        all_skater_stats.extend(
            _fetch_skater_game_stats_window(
                season_id=season_id,
                game_type=game_type,
                start_date=window_start,
                end_date=window_end,
            )
        )
        all_goalie_stats.extend(
            _fetch_goalie_game_stats_window(
                season_id=season_id,
                game_type=game_type,
                start_date=window_start,
                end_date=window_end,
            )
        )

    logger.info(f"Total: {len(all_skater_stats)} skater games, {len(all_goalie_stats)} goalie games")
    return all_skater_stats, all_goalie_stats


def fetch_skater_game_stats_range(
    season_id: str,
    start_date: Optional[Union[datetime, date]] = None,
    end_date: Optional[Union[datetime, date]] = None,
    game_type: Optional[int] = None,
) -> List[SkaterGameStats]:
    if start_date is None or end_date is None:
        start_date, end_date = _season_date_bounds(season_id)

    if isinstance(start_date, date) and not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(end_date, date) and not isinstance(end_date, datetime):
        end_date = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc)

    if start_date is None or end_date is None:
        start_date, end_date = _season_date_bounds(season_id)

    windows = _date_windows(start_date, end_date, DEFAULT_GAME_WINDOW_DAYS)
    results: List[SkaterGameStats] = []
    for window_start, window_end in windows:
        results.extend(
            _fetch_skater_game_stats_window(
                season_id=season_id,
                game_type=game_type,
                start_date=window_start,
                end_date=window_end,
            )
        )
    return results


def fetch_skater_season_summaries(
    season_id: str,
    game_type: Optional[int] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Fetch skater season summaries with paging."""
    if game_type is None:
        client = _client()
        if client is not None:
            try:
                data = client.stats.skater_stats_summary(
                    start_season=season_id,
                    end_season=season_id,
                )
                if isinstance(data, dict):
                    return data.get("data") or data.get("results") or data.get("stats") or []
                return data if isinstance(data, list) else []
            except Exception as exc:
                logger.warning("nhl-api-py skater summary failed: %s", exc)

    limit = min(limit, MAX_PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        query_context = _build_query_context(
            season_id=season_id,
            game_type=game_type,
            player_id=None,
            start=offset,
            limit=limit,
        )
        params = {
            "isAggregate": "true",
            "isGame": "false",
            "limit": limit,
            "start": offset,
            "cayenneExp": _season_cayenne_exp(season_id, game_type),
        }
        data = None
        if query_context is not None:
            data = _nhlpy_stats_call(
                report_type="summary",
                query_context=query_context,
                aggregate=True,
                method_name="skater_stats_with_query_context",
            )
        if data is None:
            data = _fetch_stats("skater/summary", params)
        if not data:
            break
        results.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return results


def fetch_goalie_season_summaries(
    season_id: str,
    game_type: Optional[int] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Fetch goalie season summaries with paging."""
    if game_type is None:
        client = _client()
        if client is not None:
            try:
                data = client.stats.goalie_stats_summary(
                    start_season=season_id,
                    end_season=season_id,
                )
                if isinstance(data, dict):
                    return data.get("data") or data.get("results") or data.get("stats") or []
                return data if isinstance(data, list) else []
            except Exception as exc:
                logger.warning("nhl-api-py goalie summary failed: %s", exc)

    limit = min(limit, MAX_PAGE_SIZE)
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        query_context = _build_query_context(
            season_id=season_id,
            game_type=game_type,
            player_id=None,
            start=offset,
            limit=limit,
        )
        params = {
            "isAggregate": "true",
            "isGame": "false",
            "limit": limit,
            "start": offset,
            "cayenneExp": _season_cayenne_exp(season_id, game_type),
        }
        data = None
        if query_context is not None:
            data = _nhlpy_stats_call(
                report_type="summary",
                query_context=query_context,
                aggregate=True,
                method_name="goalie_stats_with_query_context",
            )
        if data is None:
            data = _fetch_stats("goalie/summary", params)
        if not data:
            break
        results.extend(data)
        if len(data) < limit:
            break
        offset += limit
    return results


def _season_cayenne_exp(season_id: str, game_type: Optional[int]) -> str:
    parts = [f"seasonId={season_id}"]
    if game_type is not None:
        parts.append(f"gameTypeId={game_type}")
    return " and ".join(parts)
