"""Yahoo Fantasy API service for fetching player ownership data."""

import logging
import re
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.player import Player
from app.models.yahoo import YahooPlayerMapping, PlayerOwnershipSnapshot
from app.services.yahoo_oauth_service import get_yahoo_access_token

logger = logging.getLogger(__name__)

YAHOO_FANTASY_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
YAHOO_MAX_PLAYERS_PAGE = 25

# Yahoo game key for NHL - changes each season
# 2024-25 season game key is typically nhl.l.XXXX or just "nhl"
NHL_GAME_KEY = "nhl"

YAHOO_TEAM_MAP = {
    "ANA": "ANA",
    "ARI": "UTA",
    "BOS": "BOS",
    "BUF": "BUF",
    "CAR": "CAR",
    "CBJ": "CBJ",
    "CGY": "CGY",
    "CHI": "CHI",
    "COL": "COL",
    "DAL": "DAL",
    "DET": "DET",
    "EDM": "EDM",
    "FLA": "FLA",
    "LA": "LAK",
    "LAK": "LAK",
    "MIN": "MIN",
    "MTL": "MTL",
    "NJ": "NJD",
    "NJD": "NJD",
    "NSH": "NSH",
    "NYI": "NYI",
    "NYR": "NYR",
    "OTT": "OTT",
    "PHI": "PHI",
    "PIT": "PIT",
    "SEA": "SEA",
    "SJ": "SJS",
    "SJS": "SJS",
    "STL": "STL",
    "TB": "TBL",
    "TBL": "TBL",
    "TOR": "TOR",
    "UTA": "UTA",
    "VAN": "VAN",
    "VGK": "VGK",
    "WPG": "WPG",
    "WSH": "WSH",
}


def _extract_player_ownership_fragment(xml_text: str, player_key: str) -> str:
    if not xml_text or not player_key:
        return ""
    try:
        root = ET.fromstring(xml_text)
        ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
        for player in root.findall(".//y:player", ns):
            key_node = player.find("y:player_key", ns)
            if key_node is None or (key_node.text or "") != player_key:
                continue
            ownership = player.find("y:ownership", ns)
            if ownership is None:
                return ""
            return ET.tostring(ownership, encoding="unicode")
    except ET.ParseError:
        return ""
    return ""


def _extract_player_fragment(xml_text: str, player_key: str) -> str:
    if not xml_text or not player_key:
        return ""
    try:
        root = ET.fromstring(xml_text)
        ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
        for player in root.findall(".//y:player", ns):
            key_node = player.find("y:player_key", ns)
            if key_node is None or (key_node.text or "") != player_key:
                continue
            return ET.tostring(player, encoding="unicode")
    except ET.ParseError:
        return ""
    return ""


@dataclass
class YahooPlayerOwnership:
    """Player ownership data from Yahoo."""

    yahoo_player_key: str
    yahoo_player_id: str
    name: str
    team: str
    position: str
    ownership_percentage: float
    percent_started: float
    percent_owned_change: float


async def fetch_player_ownership(
    access_token: str,
    player_keys: list[str],
) -> list[YahooPlayerOwnership]:
    """
    Fetch ownership data for specific players.

    Args:
        access_token: Valid Yahoo OAuth access token
        player_keys: List of Yahoo player keys (e.g., "nhl.p.12345")

    Returns:
        List of ownership data for each player
    """
    if not player_keys:
        return []

    # Yahoo API allows batch requests
    keys_param = ",".join(player_keys)
    url = f"{YAHOO_FANTASY_API_BASE}/players;player_keys={keys_param}/ownership"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/xml",
            },
        )

        if response.status_code != 200:
            logger.error(f"Yahoo API error: {response.status_code} - {response.text}")
            return []

        ownership = _parse_ownership_response(response.text)
        ownership_fragment = ""
        player_fragment = ""
        if len(player_keys) == 1:
            ownership_fragment = _extract_player_ownership_fragment(response.text, player_keys[0])
            player_fragment = _extract_player_fragment(response.text, player_keys[0])
        if _should_fallback_to_percent_owned(ownership):
            percent_url = f"{YAHOO_FANTASY_API_BASE}/players;player_keys={keys_param}/percent_owned"
            percent_resp = await client.get(
                percent_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/xml",
                },
            )
            if percent_resp.status_code != 200:
                logger.error(
                    "Yahoo percent_owned error: %s - %s",
                    percent_resp.status_code,
                    percent_resp.text,
                )
                return ownership
            percent_owned = _parse_percent_owned_response(percent_resp.text)
            if len(player_keys) == 1 and _should_fallback_to_percent_owned(percent_owned):
                percent_fragment = _extract_player_ownership_fragment(percent_resp.text, player_keys[0])
                percent_player_fragment = _extract_player_fragment(percent_resp.text, player_keys[0])
                logger.warning(
                    "Yahoo percent_owned returned zeros for %s. ownership=%s percent_owned=%s player=%s percent_player=%s",
                    player_keys[0],
                    ownership_fragment or "n/a",
                    percent_fragment or "n/a",
                    player_fragment or "n/a",
                    percent_player_fragment or "n/a",
                )
            return percent_owned

        return ownership


async def fetch_league_players_ownership(
    access_token: str,
    league_key: str,
    status: str = "A",  # A=Available, T=Taken, W=Waivers
    count: int = 100,
) -> list[YahooPlayerOwnership]:
    """
    Fetch player ownership from a specific league.

    Args:
        access_token: Valid Yahoo OAuth access token
        league_key: Yahoo league key (e.g., "nhl.l.12345")
        status: Player status filter
        count: Number of players to fetch

    Returns:
        List of ownership data
    """
    url = f"{YAHOO_FANTASY_API_BASE}/league/{league_key}/players;status={status};count={count}/ownership"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/xml",
            },
        )

        if response.status_code != 200:
            logger.error(f"Yahoo API error: {response.status_code} - {response.text}")
            return []

        return _parse_ownership_response(response.text)


async def fetch_all_nhl_ownership(
    access_token: str,
    start: int = 0,
    count: int = 250,
) -> list[YahooPlayerOwnership]:
    """
    Fetch ownership data for all NHL players (paginated).

    Args:
        access_token: Valid Yahoo OAuth access token
        start: Starting index
        count: Number of players per request (max 250)

    Returns:
        List of ownership data
    """
    count = min(count, YAHOO_MAX_PLAYERS_PAGE)
    url = f"{YAHOO_FANTASY_API_BASE}/game/{NHL_GAME_KEY}/players;start={start};count={count}/ownership"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/xml",
            },
        )

        if response.status_code != 200:
            logger.error(f"Yahoo API error: {response.status_code} - {response.text}")
            return []

        ownership = _parse_ownership_response(response.text)
        if _should_fallback_to_percent_owned(ownership):
            percent_url = f"{YAHOO_FANTASY_API_BASE}/game/{NHL_GAME_KEY}/players;start={start};count={count}/percent_owned"
            percent_resp = await client.get(
                percent_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/xml",
                },
            )
            if percent_resp.status_code != 200:
                logger.error(
                    "Yahoo percent_owned error: %s - %s",
                    percent_resp.status_code,
                    percent_resp.text,
                )
                return ownership
            return _parse_percent_owned_response(percent_resp.text)

        return ownership


async def get_user_leagues(access_token: str) -> list[dict]:
    """
    Get user's Yahoo Fantasy leagues.

    Args:
        access_token: Valid Yahoo OAuth access token

    Returns:
        List of league info dicts
    """
    url = f"{YAHOO_FANTASY_API_BASE}/users;use_login=1/games;game_keys={NHL_GAME_KEY}/leagues"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/xml",
            },
        )

        if response.status_code != 200:
            logger.error(f"Yahoo API error: {response.status_code} - {response.text}")
            return []

        return _parse_leagues_response(response.text)


def _parse_ownership_response(xml_text: str) -> list[YahooPlayerOwnership]:
    """Parse Yahoo API ownership response XML."""
    ownership_list = []

    try:
        root = ET.fromstring(xml_text)
        # Yahoo uses namespaces
        ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}

        def _local_name(tag: str) -> str:
            return tag.split("}")[-1] if "}" in tag else tag

        def _safe_float_text(value: Optional[str]) -> float:
            if not value:
                return 0.0
            cleaned = value.replace("%", "").strip()
            try:
                return float(cleaned)
            except (TypeError, ValueError):
                return 0.0

        def _find_first_by_local(element: ET.Element, names: set[str]) -> Optional[ET.Element]:
            for child in element.iter():
                if _local_name(child.tag) in names:
                    return child
            return None

        def _value_from_element(element: Optional[ET.Element]) -> float:
            if element is None:
                return 0.0
            if element.text and element.text.strip():
                return _safe_float_text(element.text)
            for child in list(element):
                if _local_name(child.tag) == "value":
                    return _safe_float_text(child.text)
            return 0.0

        def _ownership_value_from_block(block: ET.Element) -> float:
            owned_node = _find_first_by_local(
                block,
                {"ownership_percent", "ownership_percentage", "percent_owned"},
            )
            if owned_node is not None:
                return _value_from_element(owned_node)
            type_node = _find_first_by_local(block, {"ownership_type"})
            value_node = _find_first_by_local(block, {"value"})
            if type_node is not None and value_node is not None:
                type_text = (type_node.text or "").lower()
                if "owned" in type_text or "percent" in type_text:
                    return _value_from_element(value_node)
            return 0.0

        def _started_value_from_block(block: ET.Element) -> float:
            started_node = _find_first_by_local(
                block,
                {"percent_started", "percent_started_value"},
            )
            if started_node is not None:
                return _value_from_element(started_node)
            return 0.0

        def _owned_change_from_block(block: ET.Element) -> float:
            change_node = _find_first_by_local(
                block,
                {"percent_owned_change", "percent_owned_delta", "percent_owned_change_value"},
            )
            if change_node is not None:
                return _value_from_element(change_node)
            return 0.0

        for player in root.findall(".//y:player", ns):
            player_key = player.find("y:player_key", ns)
            player_id = player.find("y:player_id", ns)
            name = player.find("y:name/y:full", ns)
            team = player.find("y:editorial_team_abbr", ns)
            position = player.find("y:display_position", ns)
            ownership = player.find("y:ownership", ns)

            if ownership is not None:
                ownership_percentage = _ownership_value_from_block(ownership)
                percent_started = _started_value_from_block(ownership)
                percent_owned_change = _owned_change_from_block(ownership)

                ownership_list.append(
                    YahooPlayerOwnership(
                        yahoo_player_key=player_key.text if player_key is not None else "",
                        yahoo_player_id=player_id.text if player_id is not None else "",
                        name=name.text if name is not None else "",
                        team=team.text if team is not None else "",
                        position=position.text if position is not None else "",
                        ownership_percentage=ownership_percentage,
                        percent_started=percent_started,
                        percent_owned_change=percent_owned_change,
                    )
                )

    except ET.ParseError as e:
        logger.error(f"Failed to parse Yahoo XML: {e}")

    return ownership_list


def _parse_percent_owned_response(xml_text: str) -> list[YahooPlayerOwnership]:
    """Parse Yahoo API percent-owned response XML."""
    ownership_list = []

    try:
        root = ET.fromstring(xml_text)
        ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}

        def _local_name(tag: str) -> str:
            return tag.split("}")[-1] if "}" in tag else tag

        def _safe_float_text(value: Optional[str]) -> float:
            if not value:
                return 0.0
            cleaned = value.replace("%", "").strip()
            try:
                return float(cleaned)
            except (TypeError, ValueError):
                return 0.0

        def _value_from_element(element: Optional[ET.Element]) -> float:
            if element is None:
                return 0.0
            if element.text and element.text.strip():
                return _safe_float_text(element.text)
            for child in list(element):
                if _local_name(child.tag) == "value":
                    return _safe_float_text(child.text)
            return 0.0

        def _value_from_ownership_block(block: Optional[ET.Element]) -> float:
            if block is None:
                return 0.0
            type_node = _find_first_by_local(block, {"ownership_type"})
            value_node = _find_first_by_local(block, {"value"})
            if type_node is not None and value_node is not None:
                type_text = (type_node.text or "").lower()
                if "owned" in type_text or "percent" in type_text:
                    return _value_from_element(value_node)
            return 0.0

        def _find_first_by_local(element: ET.Element, names: set[str]) -> Optional[ET.Element]:
            for child in element.iter():
                if _local_name(child.tag) in names:
                    return child
            return None

        for player in root.findall(".//y:player", ns):
            player_key = player.find("y:player_key", ns)
            player_id = player.find("y:player_id", ns)
            name = player.find("y:name/y:full", ns)
            team = player.find("y:editorial_team_abbr", ns)
            position = player.find("y:display_position", ns)

            percent_owned = 0.0
            node = _find_first_by_local(player, {"percent_owned"})
            if node is None:
                node = _find_first_by_local(player, {"ownership_percent", "ownership_percentage"})
            percent_owned = _value_from_element(node)
            if percent_owned == 0.0:
                percent_owned = _value_from_ownership_block(player.find("y:ownership", ns))

            ownership_list.append(
                YahooPlayerOwnership(
                    yahoo_player_key=player_key.text if player_key is not None else "",
                    yahoo_player_id=player_id.text if player_id is not None else "",
                    name=name.text if name is not None else "",
                    team=team.text if team is not None else "",
                    position=position.text if position is not None else "",
                    ownership_percentage=percent_owned,
                    percent_started=0.0,
                    percent_owned_change=0.0,
                )
            )

    except ET.ParseError as e:
        logger.error(f"Failed to parse Yahoo percent-owned XML: {e}")

    return ownership_list


def _should_fallback_to_percent_owned(ownership: list[YahooPlayerOwnership]) -> bool:
    if not ownership:
        return False
    return all(
        entry.ownership_percentage == 0.0 and entry.percent_started == 0.0
        for entry in ownership
    )

def _parse_leagues_response(xml_text: str) -> list[dict]:
    """Parse Yahoo API leagues response XML."""
    leagues = []

    try:
        root = ET.fromstring(xml_text)
        ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}

        for league in root.findall(".//y:league", ns):
            league_key = league.find("y:league_key", ns)
            league_id = league.find("y:league_id", ns)
            name = league.find("y:name", ns)
            num_teams = league.find("y:num_teams", ns)
            scoring_type = league.find("y:scoring_type", ns)

            leagues.append(
                {
                    "league_key": league_key.text if league_key is not None else "",
                    "league_id": league_id.text if league_id is not None else "",
                    "name": name.text if name is not None else "",
                    "num_teams": int(num_teams.text) if num_teams is not None and num_teams.text else 0,
                    "scoring_type": scoring_type.text if scoring_type is not None else "",
                }
            )

    except ET.ParseError as e:
        logger.error(f"Failed to parse Yahoo XML: {e}")

    return leagues


async def update_player_ownership(
    db: Session,
    user: Optional[User] = None,
    scope: str = "global",
) -> int:
    """
    Update player ownership percentages from Yahoo.

    Args:
        db: Database session
        user: User with valid Yahoo tokens

    Returns:
        Number of players updated
    """
    access_token = await get_yahoo_access_token(db, user)
    if not access_token:
        logger.warning("No valid Yahoo token available")
        return 0

    updated = 0
    start = 0
    batch_size = YAHOO_MAX_PLAYERS_PAGE
    now = datetime.utcnow()

    while True:
        ownership_data = await fetch_all_nhl_ownership(
            access_token, start=start, count=batch_size
        )

        if not ownership_data:
            break

        logger.info(
            "Yahoo ownership page start=%s count=%s rows=%s",
            start,
            batch_size,
            len(ownership_data),
        )

        updated += _apply_ownership_batch(db, ownership_data, scope, now)

        db.commit()

        if len(ownership_data) < batch_size:
            break

        start += batch_size

    logger.info(f"Updated ownership for {updated} players")
    return updated


async def update_league_ownership(
    db: Session,
    user: Optional[User],
    league_key: str,
    status: str = "A",
    count: int = 100,
) -> int:
    """Update ownership for a specific league."""
    access_token = await get_yahoo_access_token(db, user)
    if not access_token:
        logger.warning("No valid Yahoo token available")
        return 0

    ownership_data = await fetch_league_players_ownership(
        access_token,
        league_key=league_key,
        status=status,
        count=count,
    )
    if not ownership_data:
        return 0

    now = datetime.utcnow()
    updated = _apply_ownership_batch(db, ownership_data, f"league:{league_key}", now)
    db.commit()
    return updated


async def update_player_ownership_for_player(
    db: Session,
    user: Optional[User],
    player_id: str,
) -> dict:
    access_token = await get_yahoo_access_token(db, user)
    if not access_token:
        return {"status": "error", "detail": "No valid Yahoo token available"}

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        return {"status": "error", "detail": "Player not found"}

    now = datetime.utcnow()
    mapping = db.query(YahooPlayerMapping).filter(
        YahooPlayerMapping.player_id == player.id
    ).first()

    ownership = None
    if mapping and mapping.yahoo_player_key:
        results = await fetch_player_ownership(access_token, [mapping.yahoo_player_key])
        ownership = results[0] if results else None

    if ownership is None:
        # Fall back to paging until we find a confident match.
        start = 0
        batch_size = YAHOO_MAX_PLAYERS_PAGE
        max_pages = 200
        for _ in range(max_pages):
            page = await fetch_all_nhl_ownership(access_token, start=start, count=batch_size)
            if not page:
                break
            for entry in page:
                normalized = _normalize_name(entry.name)
                score, _ = _score_player_match(player, normalized, entry)
                if score >= 0.6:
                    ownership = entry
                    break
            if ownership is not None:
                break
            if len(page) < batch_size:
                break
            start += batch_size

    if ownership is None:
        return {
            "status": "ok",
            "updated": 0,
            "detail": "No Yahoo match found for player",
        }

    if not mapping:
        mapping = YahooPlayerMapping(
            player_id=player.id,
            yahoo_player_id=ownership.yahoo_player_id,
            yahoo_player_key=ownership.yahoo_player_key,
            name=ownership.name,
            team_abbrev=ownership.team,
            position=ownership.position,
            match_method="manual",
            match_confidence=0.7,
            last_seen_at=now,
        )
        db.add(mapping)
        db.flush()
    else:
        mapping.yahoo_player_key = ownership.yahoo_player_key or mapping.yahoo_player_key
        mapping.yahoo_player_id = ownership.yahoo_player_id or mapping.yahoo_player_id
        mapping.last_seen_at = now

    player.ownership_percentage = ownership.ownership_percentage
    db.add(PlayerOwnershipSnapshot(
        player_id=player.id,
        yahoo_player_id=ownership.yahoo_player_id,
        scope=f"player:{player.id}",
        percent_owned=ownership.ownership_percentage,
        percent_started=ownership.percent_started,
        percent_owned_change=ownership.percent_owned_change,
        as_of=now,
    ))
    db.commit()
    return {
        "status": "ok",
        "updated": 1,
        "ownership_percentage": ownership.ownership_percentage,
        "yahoo_player_id": ownership.yahoo_player_id,
        "yahoo_player_key": ownership.yahoo_player_key,
        "yahoo_name": ownership.name,
        "yahoo_team": _normalize_team_abbrev(ownership.team),
        "yahoo_position": ownership.position,
        "percent_started": ownership.percent_started,
        "percent_owned_change": ownership.percent_owned_change,
    }


def _load_yahoo_mappings(db: Session, yahoo_ids: list[str]) -> dict[str, YahooPlayerMapping]:
    if not yahoo_ids:
        return {}
    mappings = db.query(YahooPlayerMapping).filter(
        YahooPlayerMapping.yahoo_player_id.in_(yahoo_ids)
    ).all()
    return {m.yahoo_player_id: m for m in mappings}


def _apply_ownership_batch(
    db: Session,
    ownership_data: list[YahooPlayerOwnership],
    scope: str,
    now: datetime,
) -> int:
    updated = 0
    processed = 0
    missing_mapping = 0
    missing_player = 0
    unmatched_samples: list[str] = []
    yahoo_ids = [o.yahoo_player_id for o in ownership_data if o.yahoo_player_id]
    mapping_lookup = _load_yahoo_mappings(db, yahoo_ids)

    for ownership in ownership_data:
        processed += 1
        if not ownership.yahoo_player_id:
            continue
        mapping = mapping_lookup.get(ownership.yahoo_player_id)
        if not mapping:
            mapping = _match_and_create_mapping(db, ownership, now)
            if mapping:
                mapping_lookup[ownership.yahoo_player_id] = mapping
            else:
                missing_mapping += 1
                if len(unmatched_samples) < 3:
                    sample_team = _normalize_team_abbrev(ownership.team) or "UNK"
                    sample_pos = ownership.position or "?"
                    unmatched_samples.append(f"{ownership.name} ({sample_team} {sample_pos})")
        else:
            mapping.last_seen_at = now
            mapping.name = ownership.name or mapping.name
            mapping.team_abbrev = ownership.team or mapping.team_abbrev
            mapping.position = ownership.position or mapping.position
            mapping.yahoo_player_key = ownership.yahoo_player_key or mapping.yahoo_player_key

        if not mapping:
            continue

        player = db.query(Player).filter(Player.id == mapping.player_id).first()
        if not player:
            missing_player += 1
            continue

        player.ownership_percentage = ownership.ownership_percentage
        updated += 1

        db.add(PlayerOwnershipSnapshot(
            player_id=player.id,
            yahoo_player_id=ownership.yahoo_player_id,
            scope=scope,
            percent_owned=ownership.ownership_percentage,
            percent_started=ownership.percent_started,
            percent_owned_change=ownership.percent_owned_change,
            as_of=now,
        ))

    logger.info(
        "Ownership batch processed=%s updated=%s missing_mapping=%s missing_player=%s",
        processed,
        updated,
        missing_mapping,
        missing_player,
    )
    if unmatched_samples:
        logger.info("Ownership unmatched samples: %s", ", ".join(unmatched_samples))
    return updated


def _match_and_create_mapping(
    db: Session,
    ownership: YahooPlayerOwnership,
    now: datetime,
) -> Optional[YahooPlayerMapping]:
    if not ownership.yahoo_player_id:
        return None
    player, method, confidence = _match_player(db, ownership)
    if not player:
        return None

    mapping = YahooPlayerMapping(
        player_id=player.id,
        yahoo_player_id=ownership.yahoo_player_id,
        yahoo_player_key=ownership.yahoo_player_key,
        name=ownership.name,
        team_abbrev=ownership.team,
        position=ownership.position,
        match_method=method,
        match_confidence=confidence,
        last_seen_at=now,
    )
    db.add(mapping)
    db.flush()
    return mapping


def _match_player(
    db: Session,
    ownership: YahooPlayerOwnership,
) -> tuple[Optional[Player], Optional[str], Optional[float]]:
    normalized = _normalize_name(ownership.name)
    if not normalized:
        return None, None, None
    normalized_team = _normalize_team_abbrev(ownership.team)
    name_parts = normalized.split(" ")
    last_name = name_parts[-1] if name_parts else normalized

    query = db.query(Player).filter(Player.is_active == True)
    if normalized_team:
        query = query.filter(Player.team == normalized_team)
    candidates = query.filter(Player.name.ilike(f"%{last_name}%")).all()
    if not candidates:
        candidates = (
            db.query(Player)
            .filter(Player.name.ilike(f"%{last_name}%"))
            .all()
        )
    if not candidates:
        # Fall back to scanning active roster when accent-sensitive LIKE misses.
        candidates = query.all() if normalized_team else db.query(Player).filter(
            Player.is_active == True
        ).all()

    best = None
    best_score = 0.0
    best_method = None

    for candidate in candidates:
        score, method = _score_player_match(candidate, normalized, ownership)
        if score > best_score:
            best = candidate
            best_score = score
            best_method = method

    if best and best_score >= 0.6:
        return best, best_method, best_score
    return None, None, None


def _score_player_match(
    player: Player,
    normalized_name: str,
    ownership: YahooPlayerOwnership,
) -> tuple[float, str]:
    player_name = _normalize_name(player.name)
    score = 0.0
    method = "name_partial"

    if player_name == normalized_name:
        score = 0.9
        method = "name_exact"
    elif player_name and normalized_name and (
        player_name in normalized_name or normalized_name in player_name
    ):
        score = 0.75
        method = "name_contains"

    if ownership.team and _normalize_team_abbrev(ownership.team) == player.team:
        score += 0.1
    if ownership.position and ownership.position in (player.position or ""):
        score += 0.08

    return min(score, 0.99), method


def _normalize_name(value: str) -> str:
    value = value or ""
    value = value.lower()
    # Strip diacritics so "Stützle" -> "stutzle" instead of "sttzle".
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalize_team_abbrev(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = value.strip().upper()
    return YAHOO_TEAM_MAP.get(normalized, normalized)
