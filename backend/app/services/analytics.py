from typing import List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.player import Player, PlayerGameStats, PlayerRollingStats
from app.services.season import current_season_id, current_game_type


class AnalyticsService:
    WINDOW_SIZES = {
        "L5": 5,
        "L10": 10,
        "L20": 20,
        "Season": None,
    }

    logger = logging.getLogger(__name__)

    @staticmethod
    def compute_rolling_stats(
        db: Session,
        player: Player,
        window: str = "L10",
        season_id: Optional[str] = None,
        game_type: Optional[int] = None,
    ) -> PlayerRollingStats:
        """Compute rolling statistics for a player."""
        season_id = season_id or current_season_id()
        game_type = game_type if game_type is not None else current_game_type()
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
            )
        else:
            return AnalyticsService._compute_skater_stats(
                player,
                game_stats,
                trend_games,
                window,
                season_id,
                game_type,
            )

    @staticmethod
    def _compute_skater_stats(
        player: Player,
        game_stats: List[PlayerGameStats],
        trend_games: List[PlayerGameStats],
        window: str,
        season_id: str,
        game_type: int,
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
        streamer_score = AnalyticsService._calculate_streamer_score(
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
        streamer_score = AnalyticsService._calculate_goalie_streamer_score(
            sv_pct,
            gaa,
            total_wins,
            games_played,
            games_started,
            expected_games,
            trend,
            player.ownership_percentage,
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
    ) -> float:
        def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
            return max(min_value, min(value, max_value))

        def scaled(value: float, cap: float, weight: float) -> float:
            if cap <= 0:
                return 0.0
            return clamp(value / cap) * weight

        is_defense = position == "D"
        if is_defense:
            weights = {
                "ppg": 17.0,
                "spg": 12.0,
                "ppp": 10.0,
                "toi": 15.0,
                "plus_minus": 5.0,
                "hits_blocks": 10.0,
            }
            caps = {
                "ppg": 1.0,
                "spg": 2.6,
                "ppp": 0.6,
                "toi": 24.0,
                "hits_blocks": 5.0,
            }
        else:
            weights = {
                "ppg": 17.0,
                "spg": 17.0,
                "ppp": 5.0,
                "toi": 24.0,
                "plus_minus": 5.0,
                "hits_blocks": 5.0,
            }
            caps = {
                "ppg": 1.4,
                "spg": 3.0,
                "ppp": 0.5,
                "toi": 21.0,
                "hits_blocks": 4.0,
            }

        score = 0.0
        score += scaled(ppg, caps["ppg"], weights["ppg"])
        score += scaled(spg, caps["spg"], weights["spg"])
        score += scaled(ppp_pg, caps["ppp"], weights["ppp"])
        score += scaled(toi_pg, caps["toi"], weights["toi"])
        score += scaled(hpg + bpg, caps["hits_blocks"], weights["hits_blocks"])

        pm_score = clamp((pm_pg + 1.0) / 2.0)
        score += pm_score * weights["plus_minus"]

        if trend == "hot":
            score += 15.0
        elif trend == "stable":
            score += 5.0

        if is_defense:
            toi_gate_floor = 16.0
        else:
            toi_gate_floor = 14.0
        toi_gate_range = caps["toi"] - toi_gate_floor
        if toi_gate_range > 0:
            toi_gate = clamp((toi_pg - toi_gate_floor) / toi_gate_range)
        else:
            toi_gate = 1.0

        availability = clamp((100.0 - ownership) / 100.0) * 14.0
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
    ) -> float:
        def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
            return max(min_value, min(value, max_value))

        if gp <= 0:
            return 0.0

        score = 0.0
        sv_score = clamp((sv_pct - 0.88) / 0.05) * 20.0
        gaa_score = clamp((3.5 - gaa) / 1.5) * 15.0
        win_rate = wins / gp if gp > 0 else 0.0
        win_score = clamp(win_rate) * 18.0
        denom_games = expected_games if expected_games and expected_games > 0 else gp
        start_rate = games_started / denom_games if denom_games > 0 else 0.0
        start_score = clamp(start_rate) * 17.0

        score += sv_score + gaa_score + win_score + start_score

        if trend == "hot":
            score += 15.0
        elif trend == "stable":
            score += 5.0

        availability = clamp((100.0 - ownership) / 100.0) * 10.0
        score += availability

        sample_factor = 0.7 if gp <= 1 else 1.0

        score *= sample_factor
        return min(score, 100.0)

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
    def update_all_rolling_stats(db: Session) -> int:
        """Update rolling stats for all players. Returns count updated."""
        season_id = current_season_id()
        game_type = current_game_type()
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
