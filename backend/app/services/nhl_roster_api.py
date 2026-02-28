"""
NHL roster API client for fetching active team rosters.

Uses api-web.nhle.com/v1 endpoints which are updated daily for call-ups/assignments.
"""

from typing import Any, Dict, List, Optional
import logging
import httpx

try:
    from nhlpy import NHLClient
except Exception:  # pragma: no cover - nhlpy may be missing in some local environments
    NHLClient = None


logger = logging.getLogger(__name__)

ROSTER_API_BASE = "https://api-web.nhle.com/v1"

# Fallback list if team endpoint is unavailable.
FALLBACK_TEAM_ABBREVS = [
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL",
    "DAL", "DET", "EDM", "FLA", "LAK", "MIN", "MTL", "NJD",
    "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
    "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
]


def _client() -> Optional["NHLClient"]:
    if NHLClient is None:
        return None
    return NHLClient()


def _fetch_json(path: str) -> Optional[Dict[str, Any]]:
    url = f"{ROSTER_API_BASE}/{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.error(f"Roster API error for {path}: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Unexpected roster API error for {path}: {exc}")
        return None


def fetch_team_abbrevs(client: Optional["NHLClient"] = None) -> List[str]:
    """Fetch NHL team abbreviations, falling back to a static list."""
    teams_payload = None
    if client is not None:
        try:
            teams_payload = client.teams.teams()
        except Exception as exc:
            logger.error(f"NHLClient teams error: {exc}")

    if not teams_payload:
        teams_payload = _fetch_json("teams")
    if not teams_payload:
        return FALLBACK_TEAM_ABBREVS

    if isinstance(teams_payload, dict):
        teams = teams_payload.get("teams") or teams_payload.get("data") or []
    else:
        teams = teams_payload or []
    abbrevs: List[str] = []
    for team in teams:
        abbrev = team.get("abbrev") or team.get("triCode") or team.get("teamAbbrev") or team.get("abbreviation")
        if isinstance(abbrev, str):
            abbrevs.append(abbrev.strip())

    return sorted(set(abbrevs)) if abbrevs else FALLBACK_TEAM_ABBREVS


def fetch_team_roster(
    team_abbrev: str,
    season_id: str,
    client: Optional["NHLClient"] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch roster for a team and season."""
    payload = None
    if client is not None:
        try:
            payload = client.teams.team_roster(team_abbr=team_abbrev, season=season_id)
        except Exception as exc:
            logger.error(f"NHLClient roster error for {team_abbrev}: {exc}")
    if not payload:
        payload = _fetch_json(f"roster/{team_abbrev}/{season_id}")
    if not payload:
        return {}
    return payload


def fetch_all_rosters(season_id: str) -> List[Dict[str, Any]]:
    """Fetch all team rosters for a season."""
    client = _client()
    roster_entries: List[Dict[str, Any]] = []
    for abbrev in fetch_team_abbrevs(client):
        roster = fetch_team_roster(abbrev, season_id, client)
        if not roster:
            continue

        for group_key in ("forwards", "defensemen", "goalies", "skaters", "roster"):
            players = roster.get(group_key) or []
            for player in players:
                if not isinstance(player, dict):
                    continue
                entry = dict(player)
                entry["teamAbbrev"] = abbrev
                roster_entries.append(entry)

    return roster_entries
