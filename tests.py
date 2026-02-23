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
    res = client.post("/api/players", json={"steam_id": "76561198000000001"})
    assert res.status_code == 201
    data = res.get_json()
    assert data["steam_id"] == "76561198000000001"
    assert data["username"] == "76561198000000001"


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


def test_openai_client_no_key():
    from openai_client import generate_analysis
    result = generate_analysis([{"username": "player1", "games": 1, "avg_rating": 1.0,
                                  "avg_kd": 1.2, "avg_adr": 75.0, "avg_hs_pct": 40.0,
                                  "win_rate": 50.0}],
                                scope="all time", openai_api_key="")
    assert "OpenAI API key is not configured" in result


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
    client.post("/api/players", json={"steam_id": "76561198000000001"})

    client.post("/api/sync", json={})
    client.post("/api/sync", json={})

    sessions = client.get("/api/sessions").get_json()
    assert len(sessions) == 1


# ------------------------------------------------------------------ #
# Steam client unit tests                                              #
# ------------------------------------------------------------------ #

def test_steam_parse_summary():
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
