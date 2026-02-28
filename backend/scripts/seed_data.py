"""
Seed script to populate the database with mock NHL players and game data.
Run with: python -m scripts.seed_data
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import random
import uuid

from app.database import SessionLocal, engine, Base
from app.models import Player, Game, PlayerGameStats, PlayerRollingStats, User
from app.services.analytics import AnalyticsService
from app.services.season import season_id_for_date, current_game_type


# Mock player data
PLAYERS_DATA = [
    # Elite players
    {"name": "Connor McDavid", "team": "EDM", "position": "C", "number": 97, "score": 95, "ownership": 99},
    {"name": "Auston Matthews", "team": "TOR", "position": "C", "number": 34, "score": 92, "ownership": 98},
    {"name": "Nathan MacKinnon", "team": "COL", "position": "C", "number": 29, "score": 91, "ownership": 97},
    {"name": "Nikita Kucherov", "team": "TBL", "position": "RW", "number": 86, "score": 90, "ownership": 96},
    {"name": "Leon Draisaitl", "team": "EDM", "position": "C", "number": 29, "score": 89, "ownership": 95},
    {"name": "Cale Makar", "team": "COL", "position": "D", "number": 8, "score": 88, "ownership": 94},
    {"name": "David Pastrnak", "team": "BOS", "position": "RW", "number": 88, "score": 87, "ownership": 93},
    {"name": "Mikko Rantanen", "team": "COL", "position": "RW", "number": 96, "score": 85, "ownership": 90},
    {"name": "Kirill Kaprizov", "team": "MIN", "position": "LW", "number": 97, "score": 84, "ownership": 88},
    {"name": "Matthew Tkachuk", "team": "FLA", "position": "LW", "number": 19, "score": 83, "ownership": 87},

    # Mid-tier streamers
    {"name": "Tage Thompson", "team": "BUF", "position": "C", "number": 72, "score": 78, "ownership": 75},
    {"name": "Jake Guentzel", "team": "TBL", "position": "LW", "number": 59, "score": 76, "ownership": 72},
    {"name": "Filip Forsberg", "team": "NSH", "position": "LW", "number": 9, "score": 74, "ownership": 68},
    {"name": "Brady Tkachuk", "team": "OTT", "position": "LW", "number": 7, "score": 73, "ownership": 65},
    {"name": "Jack Hughes", "team": "NJD", "position": "C", "number": 86, "score": 72, "ownership": 62},

    # Streamers with potential
    {"name": "Cole Caufield", "team": "MTL", "position": "RW", "number": 22, "score": 68, "ownership": 45},
    {"name": "Trevor Zegras", "team": "ANA", "position": "C", "number": 11, "score": 65, "ownership": 38},
    {"name": "Matty Beniers", "team": "SEA", "position": "C", "number": 10, "score": 62, "ownership": 32},
    {"name": "Mason McTavish", "team": "ANA", "position": "C", "number": 37, "score": 60, "ownership": 28},
    {"name": "Dylan Guenther", "team": "UTA", "position": "RW", "number": 11, "score": 58, "ownership": 22},

    # Bangers specialists
    {"name": "Ryan Reaves", "team": "TOR", "position": "RW", "number": 75, "score": 45, "ownership": 8},
    {"name": "Nicolas Deslauriers", "team": "PHI", "position": "LW", "number": 44, "score": 42, "ownership": 5},
    {"name": "Radko Gudas", "team": "ANA", "position": "D", "number": 7, "score": 48, "ownership": 12},
    {"name": "Tom Wilson", "team": "WSH", "position": "RW", "number": 43, "score": 55, "ownership": 35},
    {"name": "Ryan Lomberg", "team": "FLA", "position": "LW", "number": 94, "score": 40, "ownership": 4},

    # Goalies
    {"name": "Connor Hellebuyck", "team": "WPG", "position": "G", "number": 37, "score": 92, "ownership": 95},
    {"name": "Igor Shesterkin", "team": "NYR", "position": "G", "number": 31, "score": 90, "ownership": 93},
    {"name": "Andrei Vasilevskiy", "team": "TBL", "position": "G", "number": 88, "score": 88, "ownership": 90},
    {"name": "Jake Oettinger", "team": "DAL", "position": "G", "number": 29, "score": 82, "ownership": 78},
    {"name": "Stuart Skinner", "team": "EDM", "position": "G", "number": 74, "score": 75, "ownership": 55},
    {"name": "Pyotr Kochetkov", "team": "CAR", "position": "G", "number": 52, "score": 70, "ownership": 42},
    {"name": "Ukko-Pekka Luukkonen", "team": "BUF", "position": "G", "number": 1, "score": 65, "ownership": 28},
]

TEAMS = ["EDM", "TOR", "COL", "TBL", "BOS", "MIN", "FLA", "BUF", "NSH", "OTT",
         "NJD", "MTL", "ANA", "SEA", "UTA", "PHI", "WPG", "NYR", "DAL", "CAR", "WSH"]


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")


def seed_players(db):
    """Seed player data."""
    players = []
    for data in PLAYERS_DATA:
        player = Player(
            name=data["name"],
            team=data["team"],
            position=data["position"],
            number=data["number"],
            current_streamer_score=data["score"],
            ownership_percentage=data["ownership"],
        )
        db.add(player)
        players.append(player)

    db.commit()
    print(f"Created {len(players)} players.")
    return players


def seed_games(db):
    """Seed game data."""
    games = []
    today = datetime.utcnow().replace(hour=19, minute=0, second=0, microsecond=0)
    game_type = current_game_type()

    # Past games (last 25 days)
    for days_ago in range(1, 26):
        game_date = today - timedelta(days=days_ago)
        # 5-10 games per day
        num_games = random.randint(5, 10)
        teams_today = random.sample(TEAMS, num_games * 2)

        for i in range(0, len(teams_today) - 1, 2):
            game = Game(
                date=game_date,
                season_id=season_id_for_date(game_date),
                game_type=game_type,
                start_time_utc=game_date,
                home_team=teams_today[i],
                away_team=teams_today[i + 1],
                home_score=random.randint(1, 6),
                away_score=random.randint(1, 6),
                status="final",
                status_source="seed",
            )
            db.add(game)
            games.append(game)

    # Upcoming games (next 7 days)
    for days_ahead in range(0, 8):
        game_date = today + timedelta(days=days_ahead)
        num_games = random.randint(5, 10)
        teams_today = random.sample(TEAMS, num_games * 2)

        for i in range(0, len(teams_today) - 1, 2):
            game = Game(
                date=game_date,
                season_id=season_id_for_date(game_date),
                game_type=game_type,
                start_time_utc=game_date,
                home_team=teams_today[i],
                away_team=teams_today[i + 1],
                status="scheduled" if days_ahead > 0 else "in_progress",
                status_source="seed",
            )
            db.add(game)
            games.append(game)

    db.commit()
    print(f"Created {len(games)} games.")
    return games


def seed_game_stats(db, players, games):
    """Seed player game statistics."""
    final_games = [g for g in games if g.status == "final"]
    stats_count = 0
    game_type = current_game_type()

    for player in players:
        # Get games for this player's team
        player_games = [g for g in final_games if g.home_team == player.team or g.away_team == player.team]

        for game in player_games[:20]:  # Last 20 games max
            is_home = game.home_team == player.team
            opponent = game.away_team if is_home else game.home_team
            if player.position == "G":
                # Goalie stats
                shots_against = random.randint(25, 45)
                goals_against = random.randint(1, 5)
                saves = shots_against - goals_against
                win = 1 if random.random() > 0.5 else 0

                stats = PlayerGameStats(
                    player_id=player.id,
                    game_id=game.id,
                    date=game.date,
                    season_id=game.season_id,
                    game_type=game_type,
                    team_abbrev=player.team,
                    opponent_abbrev=opponent,
                    is_home=is_home,
                    saves=saves,
                    goals_against=goals_against,
                    shots_against=shots_against,
                    wins=win,
                    losses=1 - win,
                    shutouts=1 if goals_against == 0 else 0,
                )
            else:
                # Skater stats
                multiplier = player.current_streamer_score / 50.0

                goals = int(random.random() * 1.5 * multiplier)
                assists = int(random.random() * 2 * multiplier)
                shots = max(1, int(random.randint(1, 5) * multiplier))
                hits = random.randint(0, 5)
                blocks = random.randint(0, 4)

                stats = PlayerGameStats(
                    player_id=player.id,
                    game_id=game.id,
                    date=game.date,
                    season_id=game.season_id,
                    game_type=game_type,
                    team_abbrev=player.team,
                    opponent_abbrev=opponent,
                    is_home=is_home,
                    goals=goals,
                    assists=assists,
                    points=goals + assists,
                    shots=shots,
                    hits=hits,
                    blocks=blocks,
                    plus_minus=random.randint(-2, 3),
                    pim=2 if random.random() < 0.15 else 0,
                    power_play_points=1 if random.random() < 0.2 * multiplier else 0,
                    shorthanded_points=1 if random.random() < 0.03 else 0,
                    time_on_ice=random.uniform(12, 22) * 60,
                    faceoff_wins=random.randint(5, 15) if player.position == "C" else 0,
                    faceoff_losses=random.randint(5, 15) if player.position == "C" else 0,
                    takeaways=random.randint(0, 3),
                    giveaways=random.randint(0, 3),
                )

            db.add(stats)
            stats_count += 1

    db.commit()
    print(f"Created {stats_count} game stat records.")


def compute_rolling_stats(db, players):
    """Compute rolling stats for all players."""
    count = AnalyticsService.update_all_rolling_stats(db)
    print(f"Computed {count} rolling stat records.")


def seed_demo_user(db):
    """Create a demo user for testing."""
    from app.services.auth import AuthService

    demo_user = User(
        id=str(uuid.uuid4()),
        username="demo",
        email="demo@forecheck.app",
        display_name="Demo User",
        hashed_password=AuthService.get_password_hash("demo123"),
        bio="Fantasy hockey enthusiast",
    )
    db.add(demo_user)
    db.commit()
    print("Demo user created (username: demo, password: demo123)")


def main():
    """Run all seed functions."""
    print("Starting database seed...")
    print("=" * 50)

    # Create tables
    create_tables()

    # Get database session
    db = SessionLocal()

    try:
        # Check if already seeded
        existing_players = db.query(Player).count()
        if existing_players > 0:
            print(f"Database already has {existing_players} players. Skipping seed.")
            print("To reseed, delete the database file and run again.")
            return

        # Seed data
        players = seed_players(db)
        games = seed_games(db)
        seed_game_stats(db, players, games)
        compute_rolling_stats(db, players)
        seed_demo_user(db)

        print("=" * 50)
        print("Seed complete!")
        print("\nYou can now start the server with:")
        print("  uvicorn app.main:app --reload")
        print("\nAPI docs available at:")
        print("  http://localhost:8000/docs")

    finally:
        db.close()


if __name__ == "__main__":
    main()
