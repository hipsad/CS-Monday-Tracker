"""Tests for the CS Monday Tracker application."""
import json
import pytest

from app import create_app
from extensions import db as _db
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test-secret"
    LEETIFY_API_KEY = ""
    OPENAI_API_KEY = ""


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ------------------------------------------------------------------ #
# Player endpoints                                                     #
# ------------------------------------------------------------------ #

def test_list_players_empty(client):
    res = client.get("/api/players")
    assert res.status_code == 200
    assert res.get_json() == []


def test_add_player_missing_steam_id(client):
    res = client.post("/api/players", json={})
    assert res.status_code == 400
    assert "steam_id" in res.get_json()["error"]


def test_add_player_no_leetify(client, monkeypatch):
    """When Leetify is unreachable the player is still saved with the steam_id as username."""
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [])
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["steam_id"] == "76561198000000001"
    assert data["username"] == "76561198000000001"


def test_add_player_no_leetify_steam_fallback(client, monkeypatch):
    """When Leetify is unreachable and Steam API key is set, Steam provides the name."""
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [
        {"steam_id": "76561198000000001", "username": "SteamUser",
         "avatar_url": "https://steam.example.com/avatar.jpg", "profile_url": "", "real_name": ""},
    ])
    client.application.config["STEAM_API_KEY"] = "fake-steam-key"
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["username"] == "SteamUser"
    assert data["avatar_url"] == "https://steam.example.com/avatar.jpg"


def test_add_player_leetify_no_name_steam_fallback(client, monkeypatch):
    """When Leetify returns a profile without a name, Steam API provides the name."""
    fake_profile = {
        "meta": {"steam64Id": "76561198000000001", "name": "", "steamAvatarUrl": ""},
        "games": [],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [
        {"steam_id": "76561198000000001", "username": "SteamFallback",
         "avatar_url": "https://steam.example.com/avatar.jpg", "profile_url": "", "real_name": ""},
    ])
    client.application.config["STEAM_API_KEY"] = "fake-steam-key"
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["username"] == "SteamFallback"


def test_add_player_with_leetify(client, monkeypatch):
    """When Leetify returns profile data, username and avatar are stored."""
    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000001",
            "name": "FragMaster",
            "steamAvatarUrl": "https://example.com/avatar.jpg",
        },
        "games": [],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["username"] == "FragMaster"
    assert data["avatar_url"] == "https://example.com/avatar.jpg"


def test_add_player_duplicate(client, monkeypatch):
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 409


def test_remove_player(client, monkeypatch):
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    client.post("/api/players", json={"steam_id": "76561198000000099"})
    res = client.delete("/api/players/76561198000000099")
    assert res.status_code == 200
    players = client.get("/api/players").get_json()
    assert all(p["steam_id"] != "76561198000000099" for p in players)


def test_get_player_not_found(client):
    res = client.get("/api/players/00000000000000000")
    assert res.status_code == 404


# ------------------------------------------------------------------ #
# Session endpoints                                                    #
# ------------------------------------------------------------------ #

def test_create_session(client):
    res = client.post("/api/sessions", json={"name": "Monday Night", "notes": "Good games"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["name"] == "Monday Night"
    assert data["notes"] == "Good games"


def test_list_sessions(client):
    client.post("/api/sessions", json={"name": "Session 1"})
    client.post("/api/sessions", json={"name": "Session 2"})
    res = client.get("/api/sessions")
    assert res.status_code == 200
    assert len(res.get_json()) == 2


def test_current_session_no_session(client):
    res = client.get("/api/sessions/current")
    assert res.status_code == 200
    assert res.get_json()["session"] is None


def test_current_session_with_session(client):
    client.post("/api/sessions", json={"name": "Test Session"})
    res = client.get("/api/sessions/current")
    assert res.status_code == 200
    assert res.get_json()["session"]["name"] == "Test Session"


# ------------------------------------------------------------------ #
# Stats endpoints                                                      #
# ------------------------------------------------------------------ #

def test_all_time_stats_empty(client):
    res = client.get("/api/stats")
    assert res.status_code == 200
    assert res.get_json() == []


def test_problem_players_empty(client):
    res = client.get("/api/stats/problem-players")
    assert res.status_code == 200
    assert res.get_json() == []


def test_stats_after_sync(client, monkeypatch, app):
    """After a sync, per-player stats should be available."""
    from datetime import datetime

    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000001",
            "name": "FragMaster",
            "steamAvatarUrl": "",
        },
        "games": [
            {
                "gameId": "match-abc-123",
                "mapName": "de_dust2",
                "gameFinishedAt": "2024-03-04T20:00:00Z",
                "scores": [16, 10],
            }
        ],
    }

    fake_game_details = {
        "playerStats": [
            {
                "steam64Id": "76561198000000001",
                "totalKills": 25,
                "totalDeaths": 14,
                "totalAssists": 3,
                "shotsHitFoeHead": 10,
                "totalDamage": 2310.0,
                "personalPerformanceRating": 1.32,
                "leetifyRating": 0.65,
                "ctLeetifyRating": 1.40,
                "tLeetifyRating": 1.20,
                "openingKills": 4,
                "openingDeaths": 2,
                "utilityDamage": 45.0,
            }
        ],
        "teams": [{"score": 16}, {"score": 10}],
    }

    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("leetify.get_game_details", lambda *a, **kw: fake_game_details)
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    sync_res = client.post("/api/sync", json={})
    assert sync_res.status_code == 200

    stats_res = client.get("/api/stats")
    players = stats_res.get_json()
    assert len(players) == 1
    p = players[0]
    assert p["username"] == "FragMaster"
    assert p["games"] == 1
    assert p["total_kills"] == 25
    assert p["avg_kd"] == round(25 / 14, 2)


# ------------------------------------------------------------------ #
# AI Analysis endpoint                                                 #
# ------------------------------------------------------------------ #

def test_analysis_no_data(client):
    res = client.post("/api/analysis", json={"scope": "all_time"})
    assert res.status_code == 400


def test_analysis_no_openai_key(client, monkeypatch):
    """Without an OpenAI key the endpoint returns a message but still saves."""
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    # Add minimal game stats directly via DB
    with client.application.app_context():
        from models import PlayerGame, Game, Player
        from extensions import db
        player = Player.query.filter_by(steam_id="76561198000000001").first()
        game = Game(match_id="test-game-1", map_name="de_mirage", score_ct=16, score_t=8)
        db.session.add(game)
        db.session.flush()
        pg = PlayerGame(player_id=player.id, game_id=game.id, kills=20, deaths=15, rating=1.1)
        db.session.add(pg)
        db.session.commit()

    res = client.post("/api/analysis", json={"scope": "all_time"})
    assert res.status_code == 201
    data = res.get_json()
    assert "OpenAI API key is not configured" in data["analysis"]


# ------------------------------------------------------------------ #
# Leetify client unit tests                                            #
# ------------------------------------------------------------------ #

def test_parse_player_info():
    from leetify import parse_player_info
    profile = {
        "meta": {
            "steam64Id": "123",
            "name": "TestUser",
            "steamAvatarUrl": "http://img.png",
        }
    }
    info = parse_player_info(profile)
    assert info["steam_id"] == "123"
    assert info["username"] == "TestUser"
    assert info["avatar_url"] == "http://img.png"


def test_parse_games_empty():
    from leetify import parse_games
    assert parse_games({}) == []
    assert parse_games({"games": []}) == []


def test_parse_games_normalises_scores():
    from leetify import parse_games
    profile = {
        "games": [{
            "gameId": "g1",
            "mapName": "de_nuke",
            "gameFinishedAt": "2024-01-01T18:00:00Z",
            "scores": [13, 16],
        }]
    }
    games = parse_games(profile)
    assert len(games) == 1
    assert games[0]["map_name"] == "de_nuke"
    assert games[0]["score_ct"] == 13
    assert games[0]["score_t"] == 16


def test_parse_games_missing_date():
    from leetify import parse_games
    profile = {"games": [{"gameId": "g2", "mapName": "de_inferno", "scores": []}]}
    games = parse_games(profile)
    assert games[0]["played_at"] is None


def test_parse_game_player_stats():
    from leetify import parse_game_player_stats
    game_details = {
        "playerStats": [
            {
                "steam64Id": "76561198000000001",
                "totalKills": 20,
                "totalDeaths": 10,
                "totalAssists": 3,
                "shotsHitFoeHead": 8,
                "totalDamage": 2400.0,
                "personalPerformanceRating": 1.25,
                "leetifyRating": 0.60,
                "ctLeetifyRating": 1.30,
                "tLeetifyRating": 1.10,
                "openingKills": 2,
                "openingDeaths": 1,
                "utilityDamage": 25.0,
            }
        ],
        "teams": [{"score": 16}, {"score": 8}],
    }
    stats = parse_game_player_stats(game_details)
    assert len(stats) == 1
    s = stats[0]
    assert s["steam_id"] == "76561198000000001"
    assert s["kills"] == 20
    assert s["deaths"] == 10
    assert s["assists"] == 3
    assert s["headshots"] == 8
    assert s["adr"] == round(2400.0 / 24, 1)  # 24 total rounds = 16 + 8 team scores
    assert s["rating"] == 1.25
    assert s["leetify_rating"] == 0.60


def test_parse_games_null_games_list():
    """parse_games should return [] when games key is explicitly null."""
    from leetify import parse_games
    assert parse_games({"games": None}) == []


def test_parse_games_skips_null_entries():
    """parse_games should skip None entries in the games list without raising."""
    from leetify import parse_games
    profile = {
        "games": [
            None,
            {"gameId": "g1", "mapName": "de_dust2", "gameFinishedAt": "2024-01-01T18:00:00Z", "scores": [16, 8]},
        ]
    }
    games = parse_games(profile)
    assert len(games) == 1
    assert games[0]["match_id"] == "g1"


def test_parse_game_player_stats_null_player_stats():
    """parse_game_player_stats should return [] when playerStats is null."""
    from leetify import parse_game_player_stats
    assert parse_game_player_stats({"playerStats": None, "teams": [{"score": 10}]}) == []


def test_parse_game_player_stats_skips_null_entries():
    """parse_game_player_stats should skip None entries in playerStats without raising."""
    from leetify import parse_game_player_stats
    game_details = {
        "playerStats": [None, {"steam64Id": "123", "totalKills": 5, "totalDeaths": 3}],
        "teams": [{"score": 10}],
    }
    stats = parse_game_player_stats(game_details)
    assert len(stats) == 1
    assert stats[0]["steam_id"] == "123"
    assert stats[0]["kills"] == 5


def test_parse_game_player_stats_skips_null_teams():
    """parse_game_player_stats should ignore None team entries when computing total rounds."""
    from leetify import parse_game_player_stats
    game_details = {
        "playerStats": [{"steam64Id": "123", "totalKills": 5, "totalDamage": 300.0}],
        "teams": [None, {"score": 10}],
    }
    stats = parse_game_player_stats(game_details)
    assert len(stats) == 1
    assert stats[0]["adr"] == round(300.0 / 10, 1)


def test_parse_player_info_empty_name():
    """parse_player_info should return empty string when name is absent."""
    from leetify import parse_player_info
    info = parse_player_info({"meta": {"steam64Id": "123"}})
    assert info["username"] == ""


# ------------------------------------------------------------------ #
# New Leetify Public API format tests (snake_case fields)              #
# ------------------------------------------------------------------ #

def test_parse_player_info_new_api():
    """parse_player_info should support the new public API's top-level snake_case fields."""
    from leetify import parse_player_info
    profile = {
        "steam64_id": "76561198000000001",
        "name": "PublicAPIPlayer",
    }
    info = parse_player_info(profile)
    assert info["steam_id"] == "76561198000000001"
    assert info["username"] == "PublicAPIPlayer"
    assert info["avatar_url"] == ""  # new public API omits avatar


def test_parse_games_new_api():
    """parse_games should parse the new 'recent_matches' format with snake_case fields."""
    from leetify import parse_games
    profile = {
        "recent_matches": [
            {
                "id": "f78ae802-9044-4aa1-be47-d8e0193c4bd7",
                "finished_at": "2025-07-02T21:06:50.000Z",
                "map_name": "de_inferno",
                "score": [13, 6],
            }
        ]
    }
    games = parse_games(profile)
    assert len(games) == 1
    assert games[0]["match_id"] == "f78ae802-9044-4aa1-be47-d8e0193c4bd7"
    assert games[0]["map_name"] == "de_inferno"
    assert games[0]["score_ct"] == 13
    assert games[0]["score_t"] == 6


def test_parse_games_new_api_empty():
    """parse_games should return [] when recent_matches is empty."""
    from leetify import parse_games
    assert parse_games({"recent_matches": []}) == []
    assert parse_games({"recent_matches": None}) == []


def test_parse_game_player_stats_new_api():
    """parse_game_player_stats should handle the new public API response format.

    New format uses:
      - 'stats' key (was 'playerStats')
      - snake_case field names (steam64_id, total_kills, etc.)
      - 'team_scores' list of {team_number, score} objects (was 'teams')
      - 'dpr' for pre-computed ADR
      - 'total_hs_kills' for headshot kills (was 'shotsHitFoeHead')
      - 'leetify_rating' per match (was 'leetifyRating')
    """
    from leetify import parse_game_player_stats
    game_details = {
        "stats": [
            {
                "steam64_id": "76561199536301058",
                "total_kills": 26,
                "total_deaths": 8,
                "total_assists": 3,
                "total_hs_kills": 16,
                "shots_hit_foe_head": 0,
                "total_damage": 2573,
                "dpr": 160.81,
                "leetify_rating": 0.1232,
                "ct_leetify_rating": 0.0971,
                "t_leetify_rating": 0.2014,
                "rounds_count": 16,
            }
        ],
        "team_scores": [
            {"team_number": 2, "score": 3},
            {"team_number": 3, "score": 13},
        ],
    }
    stats = parse_game_player_stats(game_details)
    assert len(stats) == 1
    s = stats[0]
    assert s["steam_id"] == "76561199536301058"
    assert s["kills"] == 26
    assert s["deaths"] == 8
    assert s["assists"] == 3
    # total_hs_kills is used for headshots (not shots_hit_foe_head which was 0)
    assert s["headshots"] == 16
    # dpr is used directly as ADR
    assert s["adr"] == round(160.81, 1)
    # leetify_rating used for both rating (no HLTV 2.0 in new API) and leetify_rating
    assert s["leetify_rating"] == round(0.1232, 4)
    assert s["ct_rating"] == round(0.0971, 4)
    assert s["t_rating"] == round(0.2014, 4)


def test_parse_game_player_stats_new_api_team_scores():
    """Total rounds should be summed from team_scores in the new API format."""
    from leetify import parse_game_player_stats
    game_details = {
        "stats": [
            {
                "steam64_id": "123",
                "total_kills": 10,
                "total_damage": 1600.0,
                # No dpr – should fall back to total_damage / total_rounds
            }
        ],
        "team_scores": [
            {"team_number": 1, "score": 16},
            {"team_number": 2, "score": 8},
        ],
    }
    stats = parse_game_player_stats(game_details)
    assert len(stats) == 1
    assert stats[0]["adr"] == round(1600.0 / 24, 1)


def test_parse_game_player_stats_dpr_takes_priority():
    """When dpr is present, it should be used as ADR regardless of total_damage."""
    from leetify import parse_game_player_stats
    game_details = {
        "stats": [
            {
                "steam64_id": "123",
                "total_kills": 10,
                "total_damage": 9999.0,  # should be ignored
                "dpr": 88.5,
            }
        ],
        "team_scores": [{"team_number": 1, "score": 10}, {"team_number": 2, "score": 10}],
    }
    stats = parse_game_player_stats(game_details)
    assert stats[0]["adr"] == 88.5


def test_parse_game_player_stats_rounds_count_fallback():
    """rounds_count on player stats should be used as per-player ADR fallback."""
    from leetify import parse_game_player_stats
    game_details = {
        # No team_scores / teams provided
        "stats": [
            {
                "steam64_id": "123",
                "total_kills": 10,
                "total_damage": 2400.0,
                "rounds_count": 24,  # per-player fallback
            }
        ],
    }
    stats = parse_game_player_stats(game_details)
    assert stats[0]["adr"] == round(2400.0 / 24, 1)


def test_sync_with_new_api_format_captures_friend_stats(client, monkeypatch, app):
    """During sync, stats for all tracked players in the same game should be saved
    even if a friend's profile is not accessible via Leetify."""
    fake_profile_a = {
        "steam64_id": "76561198000000001",
        "name": "PlayerA",
        "recent_matches": [
            {
                "id": "shared-match-xyz",
                "map_name": "de_mirage",
                "finished_at": "2025-07-01T20:00:00Z",
                "score": [13, 8],
            }
        ],
    }
    # PlayerB's profile is unreachable (returns None)
    fake_game_details = {
        "stats": [
            {
                "steam64_id": "76561198000000001",
                "total_kills": 20,
                "total_deaths": 10,
                "total_assists": 2,
                "total_hs_kills": 8,
                "dpr": 90.0,
                "leetify_rating": 0.55,
                "ct_leetify_rating": 0.50,
                "t_leetify_rating": 0.60,
            },
            {
                "steam64_id": "76561198000000002",
                "total_kills": 15,
                "total_deaths": 12,
                "total_assists": 3,
                "total_hs_kills": 5,
                "dpr": 70.0,
                "leetify_rating": 0.40,
                "ct_leetify_rating": 0.38,
                "t_leetify_rating": 0.42,
            },
        ],
        "team_scores": [{"team_number": 1, "score": 13}, {"team_number": 2, "score": 8}],
    }

    def fake_profile(steam_id, **kw):
        if steam_id == "76561198000000001":
            return fake_profile_a
        return None  # Friend B has no Leetify profile

    monkeypatch.setattr("leetify.get_player_profile", fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("leetify.get_game_details", lambda *a, **kw: fake_game_details)

    # Add both players
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    client.post("/api/players", json={"steam_id": "76561198000000002"})

    sync_res = client.post("/api/sync", json={})
    assert sync_res.status_code == 200

    # PlayerA's stats should be present
    stats_a = client.get("/api/stats/76561198000000001").get_json()
    assert stats_a["stats"]["games"] == 1
    assert stats_a["stats"]["total_kills"] == 20

    # PlayerB's stats extracted from PlayerA's game details
    stats_b = client.get("/api/stats/76561198000000002").get_json()
    assert stats_b["stats"]["games"] == 1
    assert stats_b["stats"]["total_kills"] == 15


def test_stat_records_endpoint(client, monkeypatch, app):
    """The /api/stats/records endpoint should return best single-game performances."""
    fake_profile = {
        "steam64_id": "76561198000000001",
        "name": "RecordPlayer",
        "recent_matches": [
            {
                "id": "record-match-1",
                "map_name": "de_dust2",
                "finished_at": "2025-07-01T20:00:00Z",
                "score": [16, 10],
            }
        ],
    }
    fake_game_details = {
        "stats": [
            {
                "steam64_id": "76561198000000001",
                "total_kills": 30,
                "total_deaths": 12,
                "total_assists": 4,
                "total_hs_kills": 20,
                "dpr": 120.0,
                "leetify_rating": 1.5,
                "ct_leetify_rating": 1.4,
                "t_leetify_rating": 1.6,
            }
        ],
        "team_scores": [{"team_number": 1, "score": 16}, {"team_number": 2, "score": 10}],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("leetify.get_game_details", lambda *a, **kw: fake_game_details)

    client.post("/api/players", json={"steam_id": "76561198000000001"})
    client.post("/api/sync", json={})

    res = client.get("/api/stats/records")
    assert res.status_code == 200
    records = res.get_json()

    assert "most_kills" in records
    assert records["most_kills"]["value"] == 30
    assert records["most_kills"]["username"] == "RecordPlayer"

    assert "best_adr" in records
    assert records["best_adr"]["value"] == 120.0


# ------------------------------------------------------------------ #
# Monthly stats endpoint                                               #
# ------------------------------------------------------------------ #

def test_monthly_stats_empty(client):
    res = client.get("/api/stats/monthly")
    assert res.status_code == 200
    assert res.get_json() == []


def test_monthly_stats_with_recent_game(client, monkeypatch, app):
    """Games played within the last 30 days should appear in monthly stats."""
    from datetime import datetime, timedelta, timezone

    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000001",
            "name": "MonthlyPlayer",
            "steamAvatarUrl": "",
        },
        "games": [
            {
                "gameId": "match-monthly-1",
                "mapName": "de_mirage",
                "gameFinishedAt": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat().replace("+00:00", "Z"),
                "scores": [16, 8],
            }
        ],
    }

    fake_game_details = {
        "playerStats": [
            {
                "steam64Id": "76561198000000001",
                "totalKills": 20,
                "totalDeaths": 10,
                "totalAssists": 2,
                "shotsHitFoeHead": 8,
                "totalDamage": 2160.0,
                "personalPerformanceRating": 1.25,
                "leetifyRating": 0.60,
                "ctLeetifyRating": 1.30,
                "tLeetifyRating": 1.15,
                "openingKills": 3,
                "openingDeaths": 1,
                "utilityDamage": 30.0,
            }
        ],
        "teams": [{"score": 16}, {"score": 8}],
    }

    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("leetify.get_game_details", lambda *a, **kw: fake_game_details)
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    client.post("/api/sync", json={})

    res = client.get("/api/stats/monthly")
    assert res.status_code == 200
    players = res.get_json()
    assert len(players) == 1
    assert players[0]["username"] == "MonthlyPlayer"
    assert players[0]["games"] == 1
    assert players[0]["total_kills"] == 20


def test_monthly_stats_excludes_old_games(client, monkeypatch, app):
    """Games older than 30 days should NOT appear in monthly stats."""
    from datetime import datetime, timedelta, timezone

    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000002",
            "name": "OldPlayer",
            "steamAvatarUrl": "",
        },
        "games": [
            {
                "gameId": "match-old-1",
                "mapName": "de_dust2",
                "gameFinishedAt": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat().replace("+00:00", "Z"),
                "scores": [16, 14],
            }
        ],
    }

    fake_game_details = {
        "playerStats": [
            {
                "steam64Id": "76561198000000002",
                "totalKills": 15,
                "totalDeaths": 15,
                "totalAssists": 1,
                "shotsHitFoeHead": 5,
                "totalDamage": 2100.0,
                "personalPerformanceRating": 1.0,
                "leetifyRating": 0.5,
                "ctLeetifyRating": 1.0,
                "tLeetifyRating": 1.0,
                "openingKills": 2,
                "openingDeaths": 2,
                "utilityDamage": 20.0,
            }
        ],
        "teams": [{"score": 16}, {"score": 14}],
    }

    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("leetify.get_game_details", lambda *a, **kw: fake_game_details)
    client.post("/api/players", json={"steam_id": "76561198000000002"})
    client.post("/api/sync", json={})

    res = client.get("/api/stats/monthly")
    assert res.status_code == 200
    players = res.get_json()
    # Player exists but has 0 games in the last 30 days
    assert len(players) == 1
    assert players[0]["games"] == 0
    assert players[0]["total_kills"] == 0


# ------------------------------------------------------------------ #
# Steam friends endpoint                                               #
# ------------------------------------------------------------------ #

def test_steam_friends_no_key(client, monkeypatch):
    """When Steam API returns None (e.g. bad key), endpoint returns 400."""
    monkeypatch.setattr("steam.get_friend_list", lambda *a, **kw: None)
    res = client.get("/api/steam/friends/76561198000000001")
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_steam_friends_empty_list(client, monkeypatch):
    """A player with no friends returns an empty list."""
    monkeypatch.setattr("steam.get_friend_list", lambda *a, **kw: [])
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [])
    res = client.get("/api/steam/friends/76561198000000001")
    assert res.status_code == 200
    assert res.get_json() == []


def test_steam_friends_returns_profiles(client, monkeypatch):
    """Friends are returned with Steam profile data and tracked flag."""
    monkeypatch.setattr("steam.get_friend_list",
                        lambda *a, **kw: ["76561198000000010", "76561198000000011"])
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [
        {"steam_id": "76561198000000010", "username": "Alice",
         "avatar_url": "http://img/alice.png", "profile_url": "", "real_name": ""},
        {"steam_id": "76561198000000011", "username": "Bob",
         "avatar_url": "http://img/bob.png", "profile_url": "", "real_name": ""},
    ])
    res = client.get("/api/steam/friends/76561198000000001")
    assert res.status_code == 200
    friends = res.get_json()
    assert len(friends) == 2
    usernames = {f["username"] for f in friends}
    assert "Alice" in usernames
    assert "Bob" in usernames
    for f in friends:
        assert f["tracked"] is False


def test_steam_friends_marks_tracked(client, monkeypatch):
    """A friend who is already tracked should have tracked=True."""
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: None)
    client.post("/api/players", json={"steam_id": "76561198000000010"})

    monkeypatch.setattr("steam.get_friend_list",
                        lambda *a, **kw: ["76561198000000010"])
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [
        {"steam_id": "76561198000000010", "username": "TrackedFriend",
         "avatar_url": "", "profile_url": "", "real_name": ""},
    ])
    res = client.get("/api/steam/friends/76561198000000001")
    assert res.status_code == 200
    friends = res.get_json()
    assert friends[0]["tracked"] is True


# ------------------------------------------------------------------ #
# Auto-session creation on sync                                        #
# ------------------------------------------------------------------ #

def test_sync_auto_creates_session(client, monkeypatch):
    """Syncing without a session_id should auto-create a session for today."""
    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000001",
            "name": "AutoSession",
            "steamAvatarUrl": "",
        },
        "games": [],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    client.post("/api/players", json={"steam_id": "76561198000000001"})

    res = client.post("/api/sync", json={})
    assert res.status_code == 200

    sessions = client.get("/api/sessions").get_json()
    assert len(sessions) == 1
    assert sessions[0]["notes"] == "Auto-created by sync"


def test_sync_reuses_todays_session(client, monkeypatch):
    """Syncing twice on the same day should not create duplicate sessions."""
    fake_profile = {
        "meta": {
            "steam64Id": "76561198000000001",
            "name": "AutoSession",
            "steamAvatarUrl": "",
        },
        "games": [],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    client.post("/api/players", json={"steam_id": "76561198000000001"})

    client.post("/api/sync", json={})
    client.post("/api/sync", json={})

    sessions = client.get("/api/sessions").get_json()
    assert len(sessions) == 1


def test_sync_steam_fallback_for_name(client, monkeypatch):
    """When Leetify profile has no name during sync, Steam API provides it."""
    fake_profile = {
        "meta": {"steam64Id": "76561198000000001", "name": "", "steamAvatarUrl": ""},
        "games": [],
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    monkeypatch.setattr("steam.get_player_summaries", lambda *a, **kw: [
        {"steam_id": "76561198000000001", "username": "SteamName",
         "avatar_url": "https://steam.example.com/avatar.jpg", "profile_url": "", "real_name": ""},
    ])
    client.application.config["STEAM_API_KEY"] = "fake-steam-key"
    client.post("/api/players", json={"steam_id": "76561198000000001"})

    res = client.post("/api/sync", json={})
    assert res.status_code == 200

    players = client.get("/api/players").get_json()
    assert players[0]["username"] == "SteamName"


def test_sync_handles_null_games_list(client, monkeypatch):
    """sync should not raise when Leetify returns null for games list."""
    fake_profile = {
        "meta": {"steam64Id": "76561198000000001", "name": "Player1", "steamAvatarUrl": ""},
        "games": None,
    }
    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
    monkeypatch.setattr("leetify.get_player_matches", lambda *a, **kw: [])
    client.post("/api/players", json={"steam_id": "76561198000000001"})
    res = client.post("/api/sync", json={})
    assert res.status_code == 200
    assert res.get_json()["synced_games"] == 0


# ------------------------------------------------------------------ #
# Steam client unit tests                                              #
# ------------------------------------------------------------------ #
    from steam import _parse_summary
    raw = {
        "steamid": "76561198000000001",
        "personaname": "TestUser",
        "avatarmedium": "http://img/avatar.png",
        "profileurl": "https://steamcommunity.com/id/test/",
        "realname": "Test User",
    }
    result = _parse_summary(raw)
    assert result["steam_id"] == "76561198000000001"
    assert result["username"] == "TestUser"
    assert result["avatar_url"] == "http://img/avatar.png"
    assert result["profile_url"] == "https://steamcommunity.com/id/test/"
