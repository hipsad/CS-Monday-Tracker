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
        "steamId64": "76561198000000001",
        "name": "FragMaster",
        "steamAvatarUrl": "https://example.com/avatar.jpg",
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
        "steamId64": "76561198000000001",
        "name": "FragMaster",
        "steamAvatarUrl": "",
        "games": [
            {
                "gameId": "match-abc-123",
                "mapName": "de_dust2",
                "gameFinishedAt": "2024-03-04T20:00:00Z",
                "scores": [16, 10],
                "playerStats": [
                    {
                        "steamId64": "76561198000000001",
                        "kills": 25,
                        "deaths": 14,
                        "assists": 3,
                        "hs": 10,
                        "adr": 88.5,
                        "hltvRatingOverall": 1.32,
                        "leetifyRatingOverall": 0.65,
                        "hltvRatingCt": 1.40,
                        "hltvRatingT": 1.20,
                        "openingKills": 4,
                        "openingDeaths": 2,
                        "utilityDamageDealt": 45.0,
                        "opening": {},
                        "utility": {},
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr("leetify.get_player_profile", lambda *a, **kw: fake_profile)
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
    profile = {"steamId64": "123", "name": "TestUser", "steamAvatarUrl": "http://img.png"}
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
            "playerStats": [],
        }]
    }
    games = parse_games(profile)
    assert len(games) == 1
    assert games[0]["map_name"] == "de_nuke"
    assert games[0]["score_ct"] == 13
    assert games[0]["score_t"] == 16


def test_parse_games_missing_date():
    from leetify import parse_games
    profile = {"games": [{"gameId": "g2", "mapName": "de_inferno", "scores": [], "playerStats": []}]}
    games = parse_games(profile)
    assert games[0]["played_at"] is None


def test_openai_client_no_key():
    from openai_client import generate_analysis
    result = generate_analysis([{"username": "player1", "games": 1, "avg_rating": 1.0,
                                  "avg_kd": 1.2, "avg_adr": 75.0, "avg_hs_pct": 40.0,
                                  "win_rate": 50.0}],
                                scope="all time", openai_api_key="")
    assert "OpenAI API key is not configured" in result
