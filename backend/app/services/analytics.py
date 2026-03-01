from typing import Any, Callable, List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.player import Player, PlayerGameStats, PlayerRollingStats
from app.services.season import current_season_id, current_game_type
from app.services.streamer_score_config import (
    get_default_streamer_score_config,
    get_streamer_score_config,
)


class AnalyticsService:
    WINDOW_SIZES = {
        "L5": 5,
        "L10": 10,
        "L20": 20,
        "Season": None,
    }

    logger = logging.getLogger(__name__)
    LEAGUE_STAT_ALIASES = {
        "g": "goals",
        "goals": "goals",
        "a": "assists",
        "assists": "assists",
        "pts": "points",
        "point": "points",
        "points": "points",
        "+/-": "plus_minus",
        "plus_minus": "plus_minus",
        "plusminus": "plus_minus",
        "pim": "pim",
        "ppp": "power_play_points",
        "power_play_points": "power_play_points",
        "powerplaypoints": "power_play_points",
        "shp": "shorthanded_points",
        "shorthanded_points": "shorthanded_points",
        "sog": "shots",
        "shots": "shots",
        "shot": "shots",
        "hits": "hits",
        "hit": "hits",
        "blk": "blocks",
        "blocks": "blocks",
        "block": "blocks",
        "toi": "time_on_ice",
        "time_on_ice": "time_on_ice",
        "w": "wins",
        "wins": "wins",
        "sv%": "save_percentage",
        "sv_pct": "save_percentage",
        "save_percentage": "save_percentage",
        "gaa": "goals_against_average",
        "goals_against_average": "goals_against_average",
        "sv": "saves",
        "saves": "saves",
        "sa": "shots_against",
        "shots_against": "shots_against",
        "ga": "goals_against",
        "goals_against": "goals_against",
        "sho": "shutouts",
        "shutout": "shutouts",
        "shutouts": "shutouts",
        "gs": "starts",
        "starts": "starts",
        "goalie_starts": "starts",
        "goalie_games_started": "starts",
    }
    LEAGUE_LOWER_BETTER_STATS = {"goals_against_average", "goals_against"}
    LEAGUE_MIN_VALUES = {
        "plus_minus": -2.0,
        "save_percentage": 0.84,
        "goals_against_average": 1.2,
    }
    LEAGUE_SKATER_CAP_DEFAULTS = {
        "goals": 0.9,
        "assists": 1.0,
        "points": 1.8,
        "shots": 4.8,
        "hits": 4.0,
        "blocks": 3.2,
        "plus_minus": 2.0,
        "pim": 2.5,
        "power_play_points": 0.9,
        "shorthanded_points": 0.2,
        "time_on_ice": 25.0,
    }
    LEAGUE_GOALIE_CAP_DEFAULTS = {
        "wins": 1.0,
        "save_percentage": 0.94,
        "goals_against_average": 5.0,
        "saves": 40.0,
        "shots_against": 44.0,
        "goals_against": 5.0,
        "shutouts": 0.3,
        "starts": 1.0,
    }

    @staticmethod
    def compute_rolling_stats(
        db: Session,
        player: Player,
        window: str = "L10",
        season_id: Optional[str] = None,
        game_type: Optional[int] = None,
        score_config: Optional[dict] = None,
        league_context: Optional[dict[str, Any]] = None,
    ) -> PlayerRollingStats:
        """Compute rolling statistics for a player."""
        season_id = season_id or current_season_id()
        game_type = game_type if game_type is not None else current_game_type()
        score_config = score_config or get_streamer_score_config(db)
        window_size = AnalyticsService.WINDOW_SIZES.get(window)

        # Get game stats sorted by date
        query = (
            db.query(PlayerGameStats)
            .filter(
                PlayerGameStats.player_id == player.id,
                PlayerGameStats.season_id == season_id,
                PlayerGameStats.game_type == game_type,
            )
            .order_by(desc(PlayerGameStats.date))
        )

        if window_size:
            game_stats = query.limit(window_size).all()
        else:
            game_stats = query.all()

        trend_games = query.limit(20).all()
        games_played = len(game_stats)

        if games_played == 0:
            return AnalyticsService._empty_rolling_stats(player.id, window, season_id, game_type)

        # Check if goalie
        is_goalie = player.position == "G"

        if is_goalie:
            return AnalyticsService._compute_goalie_stats(
                player,
                game_stats,
                trend_games,
                window,
                season_id,
                game_type,
                score_config,
                league_context=league_context,
            )
        else:
            return AnalyticsService._compute_skater_stats(
                player,
                game_stats,
                trend_games,
                window,
                season_id,
                game_type,
                score_config,
                league_context=league_context,
            )

    @staticmethod
    def _compute_skater_stats(
        player: Player,
        game_stats: List[PlayerGameStats],
        trend_games: List[PlayerGameStats],
        window: str,
        season_id: str,
        game_type: int,
        score_config: dict,
        league_context: Optional[dict[str, Any]] = None,
    ) -> PlayerRollingStats:
        gp = len(game_stats)
        gp_float = float(gp)

        # Calculate totals
        total_goals = sum(g.goals for g in game_stats)
        total_assists = sum(g.assists for g in game_stats)
        total_points = sum(g.points for g in game_stats)
        total_shots = sum(g.shots for g in game_stats)
        total_hits = sum(g.hits for g in game_stats)
        total_blocks = sum(g.blocks for g in game_stats)
        total_plus_minus = sum(g.plus_minus for g in game_stats)
        total_pim = sum(g.pim for g in game_stats)
        total_ppp = sum(g.power_play_points for g in game_stats)
        total_shp = sum(g.shorthanded_points for g in game_stats)
        total_toi = sum(g.time_on_ice for g in game_stats)

        # Calculate per-game averages
        goals_pg = total_goals / gp_float
        assists_pg = total_assists / gp_float
        points_pg = total_points / gp_float
        shots_pg = total_shots / gp_float
        hits_pg = total_hits / gp_float
        blocks_pg = total_blocks / gp_float
        pm_pg = total_plus_minus / gp_float
        pim_pg = total_pim / gp_float
        ppp_pg = total_ppp / gp_float
        shp_pg = total_shp / gp_float
        toi_pg = (total_toi / gp_float) / 60.0  # Convert to minutes

        # Calculate trend
        trend = AnalyticsService._calculate_trend(trend_games, player.position)
        temperature_tag = AnalyticsService._calculate_temperature_tag(
            player.position,
            window,
            points_pg=points_pg,
            goals_pg=goals_pg,
            shots_pg=shots_pg,
            ppp_pg=ppp_pg,
            total_plus_minus=total_plus_minus,
        )

        # Calculate streamer score
        base_streamer_score = AnalyticsService._calculate_streamer_score(
            position=player.position,
            ppg=points_pg,
            spg=shots_pg,
            ppp_pg=ppp_pg,
            toi_pg=toi_pg,
            pm_pg=pm_pg,
            hpg=hits_pg,
            bpg=blocks_pg,
            trend=trend,
            ownership=player.ownership_percentage,
            score_config=score_config,
        )
        streamer_score = AnalyticsService._apply_league_influence(
            base_streamer_score=base_streamer_score,
            score_config=score_config,
            league_context=league_context,
            games_played=gp,
            player_position=player.position,
            metrics={
                "goals": goals_pg,
                "assists": assists_pg,
                "points": points_pg,
                "shots": shots_pg,
                "hits": hits_pg,
                "blocks": blocks_pg,
                "plus_minus": pm_pg,
                "pim": pim_pg,
                "power_play_points": ppp_pg,
                "shorthanded_points": shp_pg,
                "time_on_ice": toi_pg,
            },
        )

        # Check if rolling stats exist, update or create
        existing = None  # Would query from DB in real implementation

        stats = PlayerRollingStats(
            player_id=player.id,
            window=window,
            season_id=season_id,
            game_type=game_type,
            window_size=AnalyticsService.WINDOW_SIZES.get(window),
            games_played=gp,
            goalie_games_started=0,
            computed_at=datetime.utcnow(),
            last_game_date=game_stats[0].date if game_stats else None,
            goals_per_game=goals_pg,
            assists_per_game=assists_pg,
            points_per_game=points_pg,
            shots_per_game=shots_pg,
            hits_per_game=hits_pg,
            blocks_per_game=blocks_pg,
            plus_minus_per_game=pm_pg,
            pim_per_game=pim_pg,
            power_play_points_per_game=ppp_pg,
            shorthanded_points_per_game=shp_pg,
            time_on_ice_per_game=toi_pg,
            total_goals=total_goals,
            total_assists=total_assists,
            total_points=total_points,
            total_shots=total_shots,
            total_hits=total_hits,
            total_blocks=total_blocks,
            total_plus_minus=total_plus_minus,
            total_pim=total_pim,
            total_power_play_points=total_ppp,
            total_shorthanded_points=total_shp,
            trend_direction=trend,
            temperature_tag=temperature_tag,
            streamer_score=streamer_score,
        )

        return stats

    @staticmethod
    def _compute_goalie_stats(
        player: Player,
        game_stats: List[PlayerGameStats],
        trend_games: List[PlayerGameStats],
        window: str,
        season_id: str,
        game_type: int,
        score_config: dict,
        league_context: Optional[dict[str, Any]] = None,
    ) -> PlayerRollingStats:
        played_games = [g for g in game_stats if (g.time_on_ice or 0) > 0]
        games_played = len(played_games)
        games_started = sum(1 for g in game_stats if (g.time_on_ice or 0) >= 2400)

        total_saves = sum(g.saves or 0 for g in played_games)
        total_shots_against = sum(g.shots_against or 0 for g in played_games)
        total_goals_against = sum(g.goals_against or 0 for g in played_games)
        total_wins = sum(g.wins or 0 for g in played_games)
        total_shutouts = sum(g.shutouts or 0 for g in played_games)

        sv_pct = total_saves / total_shots_against if total_shots_against > 0 else 0
        gaa = total_goals_against / games_played if games_played > 0 else 0

        trend = AnalyticsService._calculate_trend(trend_games, player.position)
        temperature_tag = AnalyticsService._calculate_temperature_tag(
            player.position,
            window,
            wins=total_wins,
            save_percentage=sv_pct,
            games_started=games_started,
        )
        expected_games = AnalyticsService.WINDOW_SIZES.get(window) or games_played
        base_streamer_score = AnalyticsService._calculate_goalie_streamer_score(
            sv_pct,
            gaa,
            total_wins,
            games_played,
            games_started,
            expected_games,
            trend,
            player.ownership_percentage,
            score_config=score_config,
        )
        streamer_score = AnalyticsService._apply_league_influence(
            base_streamer_score=base_streamer_score,
            score_config=score_config,
            league_context=league_context,
            games_played=games_played,
            player_position=player.position,
            metrics={
                "wins": (total_wins / games_played) if games_played > 0 else 0.0,
                "save_percentage": sv_pct,
                "goals_against_average": gaa,
                "saves": (total_saves / games_played) if games_played > 0 else 0.0,
                "shots_against": (total_shots_against / games_played) if games_played > 0 else 0.0,
                "goals_against": (total_goals_against / games_played) if games_played > 0 else 0.0,
                "shutouts": (total_shutouts / games_played) if games_played > 0 else 0.0,
                "starts": (games_started / games_played) if games_played > 0 else 0.0,
            },
        )

        stats = PlayerRollingStats(
            player_id=player.id,
            window=window,
            season_id=season_id,
            game_type=game_type,
            window_size=AnalyticsService.WINDOW_SIZES.get(window),
            games_played=games_played,
            goalie_games_started=games_started,
            computed_at=datetime.utcnow(),
            last_game_date=game_stats[0].date if game_stats else None,
            save_percentage=sv_pct,
            goals_against_average=gaa,
            goalie_wins=total_wins,
            goalie_shutouts=total_shutouts,
            total_saves=total_saves,
            total_shots_against=total_shots_against,
            total_goals_against=total_goals_against,
            trend_direction=trend,
            temperature_tag=temperature_tag,
            streamer_score=streamer_score,
        )

        return stats

    @staticmethod
    def _calculate_trend(game_stats: List[PlayerGameStats], position: str) -> str:
        if len(game_stats) < 5:
            return "stable"

        recent_games = game_stats[:5]
        window_games = game_stats[:20]
        if len(window_games) < 10:
            return "stable"

        if position == "G":
            trend_score = AnalyticsService._goalie_trend_score(recent_games, window_games)
        else:
            trend_score = AnalyticsService._skater_trend_score(recent_games, window_games, position)

        if trend_score >= 0.25:
            return "hot"
        if trend_score <= -0.25:
            return "cold"
        return "stable"

    @staticmethod
    def _skater_trend_score(
        recent_games: List[PlayerGameStats],
        window_games: List[PlayerGameStats],
        position: str,
    ) -> float:
        def per_game(games, getter):
            return sum(getter(g) for g in games) / len(games)

        def delta(recent, baseline, floor):
            denom = max(abs(baseline), floor)
            return (recent - baseline) / denom

        recent_ppg = per_game(recent_games, lambda g: g.points)
        recent_gpg = per_game(recent_games, lambda g: g.goals)
        recent_apg = per_game(recent_games, lambda g: g.assists)
        recent_spg = per_game(recent_games, lambda g: g.shots)
        recent_pppg = per_game(recent_games, lambda g: g.power_play_points)
        recent_toi = per_game(recent_games, lambda g: (g.time_on_ice or 0) / 60.0)
        recent_hits = per_game(recent_games, lambda g: g.hits)
        recent_blocks = per_game(recent_games, lambda g: g.blocks)

        window_ppg = per_game(window_games, lambda g: g.points)
        window_gpg = per_game(window_games, lambda g: g.goals)
        window_apg = per_game(window_games, lambda g: g.assists)
        window_spg = per_game(window_games, lambda g: g.shots)
        window_pppg = per_game(window_games, lambda g: g.power_play_points)
        window_toi = per_game(window_games, lambda g: (g.time_on_ice or 0) / 60.0)
        window_hits = per_game(window_games, lambda g: g.hits)
        window_blocks = per_game(window_games, lambda g: g.blocks)

        d_ppg = delta(recent_ppg, window_ppg, 0.5)
        d_gpg = delta(recent_gpg, window_gpg, 0.3)
        d_apg = delta(recent_apg, window_apg, 0.3)
        d_spg = delta(recent_spg, window_spg, 1.5)
        d_pppg = delta(recent_pppg, window_pppg, 0.2)
        d_toi = delta(recent_toi, window_toi, 12)
        d_blocks = delta(recent_blocks, window_blocks, 1.0)
        d_hits_blocks = delta((recent_hits + recent_blocks) / 2, (window_hits + window_blocks) / 2, 1.0)

        if position == "D":
            weights = {
                "pppg": 0.25,
                "ppg": 0.20,
                "spg": 0.15,
                "toi": 0.20,
                "apg": 0.05,
                "gpg": 0.05,
                "blocks": 0.10,
            }
            return (
                d_pppg * weights["pppg"]
                + d_ppg * weights["ppg"]
                + d_spg * weights["spg"]
                + d_toi * weights["toi"]
                + d_apg * weights["apg"]
                + d_gpg * weights["gpg"]
                + d_blocks * weights["blocks"]
            )

        weights = {
            "ppg": 0.30,
            "gpg": 0.20,
            "apg": 0.10,
            "spg": 0.15,
            "toi": 0.15,
            "pppg": 0.05,
            "hits_blocks": 0.05,
        }
        return (
            d_ppg * weights["ppg"]
            + d_gpg * weights["gpg"]
            + d_apg * weights["apg"]
            + d_spg * weights["spg"]
            + d_toi * weights["toi"]
            + d_pppg * weights["pppg"]
            + d_hits_blocks * weights["hits_blocks"]
        )

    @staticmethod
    def _goalie_trend_score(
        recent_games: List[PlayerGameStats],
        window_games: List[PlayerGameStats],
    ) -> float:
        hot_sv_floor = 0.915
        cold_sv_ceiling = 0.905
        hot_gaa_ceiling = 3.0
        cold_gaa_floor = 3.2

        def goalie_slice(games):
            played = [g for g in games if (g.time_on_ice or 0) > 0]
            gp = len(played)
            if gp == 0:
                return 0.0, 0.0, 0.0, 0.0
            saves = sum(g.saves or 0 for g in played)
            shots = sum(g.shots_against or 0 for g in played)
            goals = sum(g.goals_against or 0 for g in played)
            wins = sum(g.wins or 0 for g in played)
            sv_pct = saves / shots if shots > 0 else 0.0
            gaa = goals / gp
            win_rate = wins / gp
            starts = sum(1 for g in played if (g.time_on_ice or 0) >= 2400)
            start_rate = starts / gp
            return sv_pct, gaa, win_rate, start_rate

        recent_sv, recent_gaa, recent_wr, recent_sr = goalie_slice(recent_games)
        window_sv, window_gaa, window_wr, window_sr = goalie_slice(window_games)

        sv_delta = (recent_sv - window_sv) / 0.01
        gaa_delta = (window_gaa - recent_gaa) / 0.10
        win_rate_delta = (recent_wr - window_wr) / 0.20
        start_rate_delta = (recent_sr - window_sr) / 0.20

        trend_score = (
            sv_delta * 0.45
            + gaa_delta * 0.25
            + win_rate_delta * 0.15
            + start_rate_delta * 0.15
        )

        # Guardrails: avoid hot/cold labels when absolute performance is still solid.
        if trend_score >= 0.25:
            if recent_sv < hot_sv_floor or recent_gaa > hot_gaa_ceiling:
                return 0.0
        if trend_score <= -0.25:
            if recent_sv > cold_sv_ceiling and recent_gaa < cold_gaa_floor:
                return 0.0

        return trend_score

    @staticmethod
    def _calculate_temperature_tag(
        position: str,
        window: str,
        points_pg: float = 0.0,
        goals_pg: float = 0.0,
        shots_pg: float = 0.0,
        ppp_pg: float = 0.0,
        total_plus_minus: int = 0,
        wins: int = 0,
        save_percentage: float = 0.0,
        games_started: int = 0,
    ) -> str:
        if window != "L5":
            return "stable"

        if position == "G":
            if games_started >= 3 and save_percentage > 0.920:
                return "hot"
            if save_percentage < 0.900 or wins < 1:
                return "cold"
            return "stable"

        if position == "D":
            if ppp_pg > 0.5 or points_pg > 1.0 or shots_pg > 3.0:
                return "hot"
            if (
                total_plus_minus <= 0
                and ppp_pg < 0.4
                and points_pg < 0.4
                and shots_pg < 2.0
            ):
                return "cold"
            return "stable"

        if points_pg > 2.0 or goals_pg > 1.0 or shots_pg > 4.0:
            return "hot"
        if points_pg < 0.5 and goals_pg <= 0.0 and shots_pg < 2.0:
            return "cold"
        return "stable"

    @staticmethod
    def _calculate_streamer_score(
        position: str,
        ppg: float,
        spg: float,
        ppp_pg: float,
        toi_pg: float,
        pm_pg: float,
        hpg: float,
        bpg: float,
        trend: str,
        ownership: float,
        score_config: Optional[dict] = None,
    ) -> float:
        def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
            return max(min_value, min(value, max_value))

        def scaled(value: float, cap: float, weight: float) -> float:
            if cap <= 0:
                return 0.0
            return clamp(value / cap) * weight

        config = score_config or get_default_streamer_score_config()
        skater_cfg = config.get("skater", {})
        weights = skater_cfg.get("weights", {})
        caps_cfg = skater_cfg.get("caps", {})
        toggles = skater_cfg.get("toggles", {})
        toi_gate_cfg = skater_cfg.get("toi_gate", {})

        is_defense = position == "D"
        caps = caps_cfg.get("defense" if is_defense else "forward", {})

        score = 0.0
        score += scaled(ppg, caps.get("points_per_game", 1.0), weights.get("points_per_game", 0.0))
        score += scaled(spg, caps.get("shots_per_game", 1.0), weights.get("shots_per_game", 0.0))
        score += scaled(
            ppp_pg,
            caps.get("power_play_points_per_game", 1.0),
            weights.get("power_play_points_per_game", 0.0),
        )
        score += scaled(
            toi_pg,
            caps.get("time_on_ice_per_game", 1.0),
            weights.get("time_on_ice_per_game", 0.0),
        )
        if toggles.get("use_hits_blocks", True):
            score += scaled(
                hpg + bpg,
                caps.get("hits_blocks_per_game", 1.0),
                weights.get("hits_blocks_per_game", 0.0),
            )

        if toggles.get("use_plus_minus", True):
            pm_score = clamp((pm_pg + 1.0) / 2.0)
            score += pm_score * weights.get("plus_minus_per_game", 0.0)

        if toggles.get("use_trend_bonus", True):
            if trend == "hot":
                score += weights.get("trend_hot_bonus", 0.0)
            elif trend == "stable":
                score += weights.get("trend_stable_bonus", 0.0)

        if toggles.get("use_toi_gate_for_availability", True):
            toi_gate_floor = toi_gate_cfg.get("defense_floor", 16.0) if is_defense else toi_gate_cfg.get(
                "forward_floor", 14.0
            )
            toi_cap = caps.get("time_on_ice_per_game", 1.0)
            toi_gate_range = toi_cap - toi_gate_floor
            if toi_gate_range > 0:
                toi_gate = clamp((toi_pg - toi_gate_floor) / toi_gate_range)
            else:
                toi_gate = 1.0
        else:
            toi_gate = 1.0

        if toggles.get("use_availability_bonus", False):
            availability = clamp((100.0 - ownership) / 100.0) * weights.get("availability_bonus", 0.0)
            availability *= toi_gate
            score += availability

        return min(score, 100.0)

    @staticmethod
    def _calculate_goalie_streamer_score(
        sv_pct: float,
        gaa: float,
        wins: int,
        gp: int,
        games_started: int,
        expected_games: int,
        trend: str,
        ownership: float,
        score_config: Optional[dict] = None,
    ) -> float:
        def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
            return max(min_value, min(value, max_value))

        if gp <= 0:
            return 0.0

        config = score_config or get_default_streamer_score_config()
        goalie_cfg = config.get("goalie", {})
        weights = goalie_cfg.get("weights", {})
        scales = goalie_cfg.get("scales", {})
        toggles = goalie_cfg.get("toggles", {})

        score = 0.0
        sv_floor = scales.get("save_percentage_floor", 0.88)
        sv_range = scales.get("save_percentage_range", 0.05)
        gaa_ceiling = scales.get("goals_against_average_ceiling", 3.5)
        gaa_range = scales.get("goals_against_average_range", 1.5)

        sv_score = clamp((sv_pct - sv_floor) / max(sv_range, 0.0001)) * weights.get("save_percentage", 0.0)
        gaa_score = clamp((gaa_ceiling - gaa) / max(gaa_range, 0.0001)) * weights.get("goals_against_average", 0.0)
        win_rate = wins / gp if gp > 0 else 0.0
        win_score = clamp(win_rate) * weights.get("wins", 0.0)
        denom_games = expected_games if expected_games and expected_games > 0 else gp
        start_rate = games_started / denom_games if denom_games > 0 else 0.0
        start_score = clamp(start_rate) * weights.get("starts", 0.0)

        score += sv_score + gaa_score + win_score + start_score

        if toggles.get("use_trend_bonus", True):
            if trend == "hot":
                score += weights.get("trend_hot_bonus", 0.0)
            elif trend == "stable":
                score += weights.get("trend_stable_bonus", 0.0)

        if toggles.get("use_availability_bonus", False):
            availability = clamp((100.0 - ownership) / 100.0) * weights.get("availability_bonus", 0.0)
            score += availability

        sample_factor = 0.7 if toggles.get("use_sample_penalty", True) and gp <= 1 else 1.0

        score *= sample_factor
        return min(score, 100.0)

    @staticmethod
    def _active_league_context(db: Session) -> Optional[dict[str, Any]]:
        from app.models.league import League

        league = (
            db.query(League)
            .filter(League.is_active == True)
            .order_by(League.updated_at.desc(), League.created_at.desc())
            .first()
        )
        if not league:
            return None
        if not isinstance(league.scoring_weights, dict) or not league.scoring_weights:
            return None
        return {
            "league_id": league.id,
            "league_type": (league.league_type or "categories").lower(),
            "scoring_weights": league.scoring_weights,
        }

    @staticmethod
    def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
        return max(min_value, min(value, max_value))

    @staticmethod
    def _normalized_league_stat(stat_key: str) -> Optional[str]:
        normalized = stat_key.strip().lower()
        normalized = normalized.replace(" ", "_")
        return AnalyticsService.LEAGUE_STAT_ALIASES.get(normalized)

    @staticmethod
    def _league_cap_map(position: str, score_config: dict) -> dict[str, float]:
        is_goalie = position == "G"
        if is_goalie:
            goalie_cfg = score_config.get("goalie", {})
            scales = goalie_cfg.get("scales", {})
            save_floor = float(scales.get("save_percentage_floor", 0.88))
            save_range = float(scales.get("save_percentage_range", 0.05))
            gaa_ceiling = float(scales.get("goals_against_average_ceiling", 3.5))
            caps = dict(AnalyticsService.LEAGUE_GOALIE_CAP_DEFAULTS)
            caps["save_percentage"] = save_floor + save_range
            caps["goals_against_average"] = max(gaa_ceiling, 0.1)
            return caps

        skater_cfg = score_config.get("skater", {})
        caps_cfg = skater_cfg.get("caps", {})
        skater_caps = caps_cfg.get("defense" if position == "D" else "forward", {})
        caps = dict(AnalyticsService.LEAGUE_SKATER_CAP_DEFAULTS)
        caps["points"] = float(skater_caps.get("points_per_game", caps["points"]))
        caps["shots"] = float(skater_caps.get("shots_per_game", caps["shots"]))
        caps["power_play_points"] = float(
            skater_caps.get("power_play_points_per_game", caps["power_play_points"])
        )
        caps["time_on_ice"] = float(skater_caps.get("time_on_ice_per_game", caps["time_on_ice"]))
        # Split combined hits+blocks cap into per-stat guidance.
        hits_blocks_cap = float(skater_caps.get("hits_blocks_per_game", 6.0))
        caps["hits"] = max(1.0, hits_blocks_cap * 0.6)
        caps["blocks"] = max(1.0, hits_blocks_cap * 0.5)
        return caps

    @staticmethod
    def _league_fit_score_categories(
        scoring_weights: dict[str, Any],
        metrics: dict[str, float],
        cap_map: dict[str, float],
    ) -> Optional[float]:
        weighted_sum = 0.0
        total_weight = 0.0

        for raw_stat, raw_weight in scoring_weights.items():
            stat = AnalyticsService._normalized_league_stat(str(raw_stat))
            if not stat or stat not in metrics:
                continue
            weight = float(raw_weight)
            abs_weight = abs(weight)
            if abs_weight <= 0:
                continue
            value = float(metrics.get(stat, 0.0))
            cap = max(0.01, float(cap_map.get(stat, 1.0)))

            if stat in AnalyticsService.LEAGUE_LOWER_BETTER_STATS:
                ratio = AnalyticsService._clamp((cap - value) / cap)
            else:
                ratio = AnalyticsService._clamp(value / cap)

            if weight < 0:
                ratio = 1.0 - ratio

            weighted_sum += ratio * abs_weight
            total_weight += abs_weight

        if total_weight <= 0:
            return None
        return AnalyticsService._clamp(weighted_sum / total_weight) * 100.0

    @staticmethod
    def _league_fit_score_points(
        scoring_weights: dict[str, Any],
        metrics: dict[str, float],
        cap_map: dict[str, float],
    ) -> Optional[float]:
        total_points = 0.0
        min_points = 0.0
        max_points = 0.0
        used = 0

        for raw_stat, raw_weight in scoring_weights.items():
            stat = AnalyticsService._normalized_league_stat(str(raw_stat))
            if not stat or stat not in metrics:
                continue
            weight = float(raw_weight)
            if weight == 0:
                continue
            used += 1
            max_value = float(cap_map.get(stat, 1.0))
            min_value = float(AnalyticsService.LEAGUE_MIN_VALUES.get(stat, 0.0))
            if max_value < min_value:
                max_value, min_value = min_value, max_value

            value = float(metrics.get(stat, 0.0))
            clamped_value = max(min_value, min(value, max_value))
            total_points += clamped_value * weight

            if weight >= 0:
                max_points += max_value * weight
                min_points += min_value * weight
            else:
                max_points += min_value * weight
                min_points += max_value * weight

        if used == 0:
            return None
        span = max_points - min_points
        if span <= 0:
            return None
        normalized = (total_points - min_points) / span
        return AnalyticsService._clamp(normalized) * 100.0

    @staticmethod
    def _calculate_league_fit_score(
        league_context: dict[str, Any],
        position: str,
        metrics: dict[str, float],
        score_config: dict[str, Any],
    ) -> Optional[float]:
        scoring_weights = league_context.get("scoring_weights")
        if not isinstance(scoring_weights, dict) or not scoring_weights:
            return None

        league_type = str(league_context.get("league_type") or "categories").lower()
        cap_map = AnalyticsService._league_cap_map(position, score_config)
        if league_type == "points":
            return AnalyticsService._league_fit_score_points(scoring_weights, metrics, cap_map)
        return AnalyticsService._league_fit_score_categories(scoring_weights, metrics, cap_map)

    @staticmethod
    def _apply_league_influence(
        base_streamer_score: float,
        score_config: dict[str, Any],
        league_context: Optional[dict[str, Any]],
        games_played: int,
        player_position: str,
        metrics: dict[str, float],
    ) -> float:
        league_cfg = score_config.get("league_influence", {})
        if not league_cfg.get("enabled", True):
            return base_streamer_score
        if not league_context:
            return base_streamer_score

        blend_weight = AnalyticsService._clamp(float(league_cfg.get("weight", 0.35)))
        if blend_weight <= 0:
            return base_streamer_score

        min_games = int(max(0, float(league_cfg.get("minimum_games", 3))))
        if min_games > 0 and games_played < min_games:
            blend_weight *= AnalyticsService._clamp(games_played / min_games)

        if blend_weight <= 0:
            return base_streamer_score

        league_fit = AnalyticsService._calculate_league_fit_score(
            league_context=league_context,
            position=player_position,
            metrics=metrics,
            score_config=score_config,
        )
        if league_fit is None:
            return base_streamer_score

        blended = ((1.0 - blend_weight) * base_streamer_score) + (blend_weight * league_fit)
        return AnalyticsService._clamp(blended, 0.0, 100.0)

    @staticmethod
    def _empty_rolling_stats(
        player_id: str,
        window: str,
        season_id: str,
        game_type: int,
    ) -> PlayerRollingStats:
        return PlayerRollingStats(
            player_id=player_id,
            window=window,
            season_id=season_id,
            game_type=game_type,
            window_size=AnalyticsService.WINDOW_SIZES.get(window),
            games_played=0,
            goalie_games_started=0,
            computed_at=datetime.utcnow(),
            trend_direction="stable",
            temperature_tag="stable",
            streamer_score=0,
            total_saves=0,
            total_shots_against=0,
            total_goals_against=0,
        )

    @staticmethod
    def update_all_rolling_stats(
        db: Session,
        score_config: Optional[dict] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        progress_every: int = 25,
    ) -> int:
        """Update rolling stats for all players. Returns count updated."""
        season_id = current_season_id()
        game_type = current_game_type()
        score_config = score_config or get_streamer_score_config(db)
        league_context = AnalyticsService._active_league_context(db)
        players = db.query(Player).filter(Player.is_active == True).all()
        count = 0
        total_players = len(players)
        started_at = datetime.utcnow()
        AnalyticsService.logger.info(
            "Rolling stats update started (%s players, season=%s, game_type=%s)",
            total_players,
            season_id,
            game_type,
        )

        for idx, player in enumerate(players, start=1):
            season_streamer_score = None
            l5_streamer_score = None
            for window in AnalyticsService.WINDOW_SIZES.keys():
                stats = AnalyticsService.compute_rolling_stats(
                    db,
                    player,
                    window,
                    season_id=season_id,
                    game_type=game_type,
                    score_config=score_config,
                    league_context=league_context,
                )

                # Update or insert
                existing = db.query(PlayerRollingStats).filter(
                    PlayerRollingStats.player_id == player.id,
                    PlayerRollingStats.window == window,
                    PlayerRollingStats.season_id == season_id,
                    PlayerRollingStats.game_type == game_type,
                ).first()

                if existing:
                    for key, value in stats.__dict__.items():
                        if not key.startswith('_'):
                            setattr(existing, key, value)
                else:
                    db.add(stats)

                if window == "Season":
                    season_streamer_score = stats.streamer_score
                if window == "L5":
                    l5_streamer_score = stats.streamer_score

                count += 1

            if l5_streamer_score is not None:
                player.current_streamer_score = l5_streamer_score
            elif season_streamer_score is not None:
                player.current_streamer_score = season_streamer_score

            if progress_callback and (idx % progress_every == 0 or idx == total_players):
                progress_callback(idx, total_players)

            if idx % 50 == 0 or idx == total_players:
                AnalyticsService.logger.info(
                    "Rolling stats progress: %s/%s players processed",
                    idx,
                    total_players,
                )

        db.commit()
        elapsed = (datetime.utcnow() - started_at).total_seconds()
        AnalyticsService.logger.info(
            "Rolling stats update finished (%s rows, %.1fs)",
            count,
            elapsed,
        )
        return count
