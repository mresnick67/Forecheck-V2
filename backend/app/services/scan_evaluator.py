from typing import List, Optional, Set
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, and_, cast, Float

from app.models.player import Player, PlayerRollingStats
from app.models.game import Game
from app.models.scan import Scan, ScanRule
from app.models.scan_alert import ScanAlertState, ScanRun
from app.services.analytics import AnalyticsService
from app.services.season import current_season_id, current_game_type


class ScanEvaluatorService:
    EASTERN_TZ = ZoneInfo("America/New_York")
    COMPARATORS = {
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        "=": lambda a, b: abs(a - b) < 0.001,
    }

    @staticmethod
    def evaluate(db: Session, scan: Scan) -> List[Player]:
        """Evaluate a scan and return matching players."""
        if not scan.rules:
            return []

        ScanEvaluatorService._ensure_rolling_stats(db, scan.rules)

        matching_ids: Optional[Set[str]] = None
        for rule in scan.rules:
            rule_ids = ScanEvaluatorService._matching_player_ids_for_rule(db, rule)
            if matching_ids is None:
                matching_ids = rule_ids
            else:
                matching_ids &= rule_ids
            if not matching_ids:
                return []

        query = db.query(Player).filter(
            Player.is_active == True,
            Player.id.in_(matching_ids),
        )

        if scan.position_filter:
            query = query.filter(Player.position == scan.position_filter)

        if scan.is_preset and scan.name == "Power Play QB":
            query = query.filter(Player.position == "D")

        players = query.order_by(Player.current_streamer_score.desc()).all()
        return players

    @staticmethod
    def _ensure_rolling_stats(db: Session, rules: List[ScanRule]) -> None:
        windows = set()
        for rule in rules:
            windows.add(rule.window)
            if rule.compare_window:
                windows.add(rule.compare_window)
        season_id = current_season_id()
        game_type = current_game_type()
        for window in windows:
            count = db.query(PlayerRollingStats).filter(
                PlayerRollingStats.window == window,
                PlayerRollingStats.season_id == season_id,
                PlayerRollingStats.game_type == game_type,
            ).count()
            if count == 0:
                AnalyticsService.update_all_rolling_stats(db)
                break

    @staticmethod
    def _matching_player_ids_for_rule(db: Session, rule: ScanRule) -> Set[str]:
        stat = rule.stat
        compare_window = rule.compare_window
        if stat == "b2b_start_opportunity":
            return ScanEvaluatorService._matching_b2b_start_ids(db, rule)
        if stat == "time_on_ice_delta":
            stat = "time_on_ice"
            if not compare_window:
                return set()

        if compare_window:
            if stat in {"ownership_percentage", "streamer_score"}:
                return set()
            primary_stats = aliased(PlayerRollingStats)
            compare_stats = aliased(PlayerRollingStats)
            primary_expr = ScanEvaluatorService._stat_expression(primary_stats, stat)
            compare_expr = ScanEvaluatorService._stat_expression(compare_stats, stat)
            if primary_expr is None or compare_expr is None:
                return set()
            delta_expr = primary_expr - compare_expr
            expr = ScanEvaluatorService._apply_comparator(delta_expr, rule.comparator, rule.value)
            query = (
                db.query(primary_stats.player_id)
                .join(Player, primary_stats.player_id == Player.id)
                .join(
                    compare_stats,
                    and_(
                        compare_stats.player_id == primary_stats.player_id,
                        compare_stats.window == compare_window,
                        compare_stats.season_id == current_season_id(),
                        compare_stats.game_type == current_game_type(),
                    ),
                )
                .filter(
                    Player.is_active == True,
                    primary_stats.window == rule.window,
                    primary_stats.season_id == current_season_id(),
                    primary_stats.game_type == current_game_type(),
                    primary_expr.isnot(None),
                    compare_expr.isnot(None),
                    expr,
                )
                .distinct()
            )
            if stat == "shooting_percentage":
                query = query.filter(Player.position != "G")
            elif stat == "saves_per_game":
                query = query.filter(Player.position == "G")
            return {row[0] for row in query.all()}

        if rule.stat == "ownership_percentage":
            query = db.query(Player.id).filter(Player.is_active == True)
            expr = ScanEvaluatorService._apply_comparator(Player.ownership_percentage, rule.comparator, rule.value)
            query = query.filter(expr)
            return {row[0] for row in query.all()}

        if rule.stat == "streamer_score":
            query = db.query(Player.id).filter(Player.is_active == True)
            expr = ScanEvaluatorService._apply_comparator(Player.current_streamer_score, rule.comparator, rule.value)
            query = query.filter(expr)
            return {row[0] for row in query.all()}

        if rule.stat == "shooting_percentage":
            column = (
                cast(PlayerRollingStats.total_goals, Float)
                / func.nullif(PlayerRollingStats.total_shots, 0)
            )
            expr = ScanEvaluatorService._apply_comparator(column, rule.comparator, rule.value)
            query = (
                db.query(PlayerRollingStats.player_id)
                .join(Player, PlayerRollingStats.player_id == Player.id)
                .filter(
                    Player.is_active == True,
                    Player.position != "G",
                    PlayerRollingStats.window == rule.window,
                    PlayerRollingStats.season_id == current_season_id(),
                    PlayerRollingStats.game_type == current_game_type(),
                    PlayerRollingStats.total_shots.isnot(None),
                    expr,
                )
                .distinct()
            )
            return {row[0] for row in query.all()}

        if rule.stat == "saves_per_game":
            column = (
                cast(PlayerRollingStats.total_saves, Float)
                / func.nullif(PlayerRollingStats.games_played, 0)
            )
            expr = ScanEvaluatorService._apply_comparator(column, rule.comparator, rule.value)
            query = (
                db.query(PlayerRollingStats.player_id)
                .join(Player, PlayerRollingStats.player_id == Player.id)
                .filter(
                    Player.is_active == True,
                    Player.position == "G",
                    PlayerRollingStats.window == rule.window,
                    PlayerRollingStats.season_id == current_season_id(),
                    PlayerRollingStats.game_type == current_game_type(),
                    PlayerRollingStats.total_saves.isnot(None),
                    expr,
                )
                .distinct()
            )
            return {row[0] for row in query.all()}

        if rule.stat == "time_on_ice_delta":
            compare_window = rule.compare_window
            if not compare_window:
                return set()
            primary_stats = aliased(PlayerRollingStats)
            compare_stats = aliased(PlayerRollingStats)
            column = primary_stats.time_on_ice_per_game - compare_stats.time_on_ice_per_game
            expr = ScanEvaluatorService._apply_comparator(column, rule.comparator, rule.value)
            query = (
                db.query(primary_stats.player_id)
                .join(Player, primary_stats.player_id == Player.id)
                .join(
                    compare_stats,
                    and_(
                        compare_stats.player_id == primary_stats.player_id,
                        compare_stats.window == compare_window,
                        compare_stats.season_id == current_season_id(),
                        compare_stats.game_type == current_game_type(),
                    ),
                )
                .filter(
                    Player.is_active == True,
                    primary_stats.window == rule.window,
                    primary_stats.season_id == current_season_id(),
                    primary_stats.game_type == current_game_type(),
                    primary_stats.time_on_ice_per_game.isnot(None),
                    compare_stats.time_on_ice_per_game.isnot(None),
                    expr,
                )
                .distinct()
            )
            return {row[0] for row in query.all()}

        column_name = ScanEvaluatorService._stat_column(rule.stat)
        if not column_name:
            return set()

        column = getattr(PlayerRollingStats, column_name)
        expr = ScanEvaluatorService._apply_comparator(column, rule.comparator, rule.value)

        query = (
            db.query(PlayerRollingStats.player_id)
            .join(Player, PlayerRollingStats.player_id == Player.id)
            .filter(
                Player.is_active == True,
                PlayerRollingStats.window == rule.window,
                PlayerRollingStats.season_id == current_season_id(),
                PlayerRollingStats.game_type == current_game_type(),
                column.isnot(None),
                expr,
            )
            .distinct()
        )
        return {row[0] for row in query.all()}

    @staticmethod
    def _matches_all_rules(db: Session, player: Player, rules: List[ScanRule]) -> bool:
        for rule in rules:
            if not ScanEvaluatorService._matches_rule(db, player, rule):
                return False
        return True

    @staticmethod
    def _matches_rule(db: Session, player: Player, rule: ScanRule) -> bool:
        stat = rule.stat
        compare_window = rule.compare_window
        if stat == "time_on_ice_delta":
            stat = "time_on_ice"
            if not compare_window:
                return False

        if compare_window:
            if stat in {"ownership_percentage", "streamer_score"}:
                return False
            primary = db.query(PlayerRollingStats).filter(
                PlayerRollingStats.player_id == player.id,
                PlayerRollingStats.window == rule.window,
                PlayerRollingStats.season_id == current_season_id(),
                PlayerRollingStats.game_type == current_game_type(),
            ).first()
            compare = db.query(PlayerRollingStats).filter(
                PlayerRollingStats.player_id == player.id,
                PlayerRollingStats.window == compare_window,
                PlayerRollingStats.season_id == current_season_id(),
                PlayerRollingStats.game_type == current_game_type(),
            ).first()
            if not primary or not compare:
                return False
            primary_value = ScanEvaluatorService._get_stat_value(primary, stat)
            compare_value = ScanEvaluatorService._get_stat_value(compare, stat)
            if primary_value is None or compare_value is None:
                return False
            delta = primary_value - compare_value
            return ScanEvaluatorService._compare(delta, rule.comparator, rule.value)

        # Handle special stats that aren't from rolling stats
        if rule.stat == "ownership_percentage":
            return ScanEvaluatorService._compare(
                player.ownership_percentage, rule.comparator, rule.value
            )
        if rule.stat == "streamer_score":
            return ScanEvaluatorService._compare(
                player.current_streamer_score, rule.comparator, rule.value
            )
        if rule.stat == "b2b_start_opportunity":
            return ScanEvaluatorService._matches_b2b_start_rule(db, player, rule)
        # Get rolling stats for the window
        rolling_stats = db.query(PlayerRollingStats).filter(
            PlayerRollingStats.player_id == player.id,
            PlayerRollingStats.window == rule.window,
            PlayerRollingStats.season_id == current_season_id(),
            PlayerRollingStats.game_type == current_game_type(),
        ).first()

        if not rolling_stats:
            return False

        stat_value = ScanEvaluatorService._get_stat_value(rolling_stats, rule.stat)
        if stat_value is None:
            return False

        return ScanEvaluatorService._compare(stat_value, rule.comparator, rule.value)

    @staticmethod
    def _stat_expression(stats: PlayerRollingStats, stat: str):
        if stat == "shooting_percentage":
            return cast(stats.total_goals, Float) / func.nullif(stats.total_shots, 0)
        if stat == "saves_per_game":
            return cast(stats.total_saves, Float) / func.nullif(stats.games_played, 0)
        column_name = ScanEvaluatorService._stat_column(stat)
        if not column_name:
            return None
        return getattr(stats, column_name)

    @staticmethod
    def _get_stat_value(stats: PlayerRollingStats, stat: str) -> Optional[float]:
        stat_mapping = {
            "goals": stats.goals_per_game,
            "assists": stats.assists_per_game,
            "points": stats.points_per_game,
            "shots": stats.shots_per_game,
            "hits": stats.hits_per_game,
            "blocks": stats.blocks_per_game,
            "plus_minus": stats.plus_minus_per_game,
            "pim": stats.pim_per_game,
            "power_play_points": stats.power_play_points_per_game,
            "shorthanded_points": stats.shorthanded_points_per_game,
            "time_on_ice": stats.time_on_ice_per_game,
            "save_percentage": stats.save_percentage,
            "goals_against_average": stats.goals_against_average,
            "wins": stats.goalie_wins,
            "shutouts": stats.goalie_shutouts,
            "goalie_starts": stats.goalie_games_started,
            "goalie_games_started": stats.goalie_games_started,
            "shooting_percentage": (
                (stats.total_goals / stats.total_shots) if stats.total_shots else 0.0
            ),
            "saves_per_game": (
                (stats.total_saves / stats.games_played) if stats.games_played else 0.0
            ),
        }
        return stat_mapping.get(stat)

    @staticmethod
    def _compare(value: float, comparator: str, target: float) -> bool:
        comp_func = ScanEvaluatorService.COMPARATORS.get(comparator)
        if not comp_func:
            return False
        return comp_func(value, target)

    @staticmethod
    def _stat_column(stat: str) -> Optional[str]:
        mapping = {
            "goals": "goals_per_game",
            "assists": "assists_per_game",
            "points": "points_per_game",
            "shots": "shots_per_game",
            "hits": "hits_per_game",
            "blocks": "blocks_per_game",
            "plus_minus": "plus_minus_per_game",
            "pim": "pim_per_game",
            "power_play_points": "power_play_points_per_game",
            "shorthanded_points": "shorthanded_points_per_game",
            "time_on_ice": "time_on_ice_per_game",
            "save_percentage": "save_percentage",
            "goals_against_average": "goals_against_average",
            "wins": "goalie_wins",
            "shutouts": "goalie_shutouts",
            "goalie_starts": "goalie_games_started",
            "goalie_games_started": "goalie_games_started",
        }
        return mapping.get(stat)

    @staticmethod
    def _apply_comparator(column, comparator: str, target: float):
        if comparator == ">":
            return column > target
        if comparator == ">=":
            return column >= target
        if comparator == "<":
            return column < target
        if comparator == "<=":
            return column <= target
        if comparator == "=":
            return func.abs(column - target) < 0.001
        return column >= target

    @staticmethod
    def _teams_with_back_to_back(db: Session, days_back: int = 1, days_ahead: int = 3) -> Set[str]:
        now = datetime.now(timezone.utc)
        today = now.astimezone(ScanEvaluatorService.EASTERN_TZ).date()
        start_day = today - timedelta(days=days_back)
        end_day = today + timedelta(days=days_ahead)
        start_utc = datetime.combine(start_day, time.min, tzinfo=ScanEvaluatorService.EASTERN_TZ).astimezone(timezone.utc)
        end_utc = datetime.combine(end_day, time.max, tzinfo=ScanEvaluatorService.EASTERN_TZ).astimezone(timezone.utc)

        games = db.query(Game).filter(
            Game.season_id == current_season_id(),
            Game.game_type == current_game_type(),
            Game.date >= start_utc,
            Game.date <= end_utc,
        ).all()

        team_days = defaultdict(set)
        for game in games:
            game_day = game.date.astimezone(ScanEvaluatorService.EASTERN_TZ).date()
            if game.home_team:
                team_days[game.home_team].add(game_day)
            if game.away_team:
                team_days[game.away_team].add(game_day)

        teams = set()
        for team, days in team_days.items():
            ordered = sorted(days)
            for idx in range(1, len(ordered)):
                if (ordered[idx] - ordered[idx - 1]).days == 1:
                    teams.add(team)
                    break
        return teams

    @staticmethod
    def _matching_b2b_start_ids(db: Session, rule: ScanRule) -> Set[str]:
        teams = ScanEvaluatorService._teams_with_back_to_back(db)
        if not teams:
            return set()
        start_stats = aliased(PlayerRollingStats)
        sv_stats = aliased(PlayerRollingStats)
        rows = (
            db.query(
                start_stats.player_id,
                start_stats.goalie_games_started,
            )
            .join(Player, start_stats.player_id == Player.id)
            .join(
                sv_stats,
                and_(
                    sv_stats.player_id == start_stats.player_id,
                    sv_stats.window == "L5",
                    sv_stats.season_id == current_season_id(),
                    sv_stats.game_type == current_game_type(),
                ),
            )
            .filter(
                Player.is_active == True,
                Player.position == "G",
                Player.team.in_(teams),
                start_stats.window == "L10",
                start_stats.season_id == current_season_id(),
                start_stats.game_type == current_game_type(),
                sv_stats.save_percentage.isnot(None),
                sv_stats.save_percentage > 0.910,
            )
            .all()
        )

        comparator = ScanEvaluatorService.COMPARATORS.get(rule.comparator)
        if not comparator:
            return set()

        matched: Set[str] = set()
        for player_id, starts in rows:
            start_rate = (starts or 0) / 10.0
            value = 1.0 if start_rate < 0.5 else 0.0
            if comparator(value, rule.value):
                matched.add(player_id)
        return matched

    @staticmethod
    def _matches_b2b_start_rule(db: Session, player: Player, rule: ScanRule) -> bool:
        if player.position != "G":
            return False
        teams = ScanEvaluatorService._teams_with_back_to_back(db)
        if player.team not in teams:
            return False
        rolling_stats = db.query(PlayerRollingStats).filter(
            PlayerRollingStats.player_id == player.id,
            PlayerRollingStats.window == "L10",
            PlayerRollingStats.season_id == current_season_id(),
            PlayerRollingStats.game_type == current_game_type(),
        ).first()
        sv_stats = db.query(PlayerRollingStats).filter(
            PlayerRollingStats.player_id == player.id,
            PlayerRollingStats.window == "L5",
            PlayerRollingStats.season_id == current_season_id(),
            PlayerRollingStats.game_type == current_game_type(),
        ).first()
        if not rolling_stats:
            return False
        if not sv_stats or sv_stats.save_percentage is None or sv_stats.save_percentage <= 0.910:
            return False
        start_rate = (rolling_stats.goalie_games_started or 0) / 10.0
        value = 1.0 if start_rate < 0.5 else 0.0
        return ScanEvaluatorService._compare(value, rule.comparator, rule.value)

    @staticmethod
    def preview_results(db: Session, scan: Scan, limit: int = 5) -> List[Player]:
        """Get a preview of scan results."""
        results = ScanEvaluatorService.evaluate(db, scan)
        return results[:limit]

    @staticmethod
    def count_matches(db: Session, scan: Scan) -> int:
        """Count how many players match the scan."""
        return len(ScanEvaluatorService.evaluate(db, scan))

    @staticmethod
    def refresh_match_counts(
        db: Session,
        scans: List[Scan],
        stale_minutes: int = 30,
        force: bool = False,
    ) -> int:
        """
        Refresh stored match_count/last_evaluated for a scan set.
        Returns the number of scans recomputed.
        """
        now = datetime.utcnow()
        updated = 0
        for scan in scans:
            last_evaluated = scan.last_evaluated
            is_stale = (
                last_evaluated is None
                or (now - last_evaluated).total_seconds() > stale_minutes * 60
            )
            if not force and not is_stale:
                continue

            results = ScanEvaluatorService.evaluate(db, scan)
            ScanEvaluatorService.record_scan_results(
                db,
                scan=scan,
                matched_players=results,
                run_at=now,
                commit=False,
            )
            updated += 1

        if updated:
            db.commit()
        return updated

    @staticmethod
    def record_scan_results(
        db: Session,
        scan: Scan,
        matched_players: List[Player],
        run_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> dict[str, int]:
        now = run_at or datetime.utcnow()
        matched_ids = {player.id for player in matched_players}
        state_rows = db.query(ScanAlertState).filter(ScanAlertState.scan_id == scan.id).all()
        state_by_player = {row.player_id: row for row in state_rows}
        previous_ids = {row.player_id for row in state_rows if row.is_current_match}

        new_ids = matched_ids - previous_ids
        dropped_ids = previous_ids - matched_ids
        staying_ids = matched_ids & previous_ids

        for player_id in new_ids:
            state = state_by_player.get(player_id)
            if not state:
                state = ScanAlertState(scan_id=scan.id, player_id=player_id)
                state_by_player[player_id] = state
                db.add(state)
            state.is_current_match = True
            state.last_matched_at = now
            state.last_notified_at = now

        for player_id in staying_ids:
            state = state_by_player.get(player_id)
            if not state:
                continue
            state.is_current_match = True
            state.last_matched_at = now

        for player_id in dropped_ids:
            state = state_by_player.get(player_id)
            if not state:
                continue
            state.is_current_match = False

        scan.last_evaluated = now
        scan.match_count = len(matched_ids)

        db.add(
            ScanRun(
                scan_id=scan.id,
                run_at=now,
                match_count=len(matched_ids),
            )
        )

        if commit:
            db.commit()

        return {
            "match_count": len(matched_ids),
            "new_count": len(new_ids),
            "dropped_count": len(dropped_ids),
        }
