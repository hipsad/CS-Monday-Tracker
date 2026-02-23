"""Leetify API client for fetching CS player and match data."""
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

LEETIFY_API_BASE = "https://api.cs-prod.leetify.com/api"


def _get(path: str, api_key: str = "", timeout: int = 15) -> dict | None:
    """Make a GET request to the Leetify API and return parsed JSON."""
    url = f"{LEETIFY_API_BASE}{path}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        logger.error("Leetify HTTP error for %s: %s", url, exc)
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("Leetify request failed for %s: %s", url, exc)
        return None


def get_player_profile(steam_id: str, api_key: str = "") -> dict | None:
    """Fetch full profile data for a player from their Steam64 ID.

    The Leetify profile endpoint returns:
      - meta.name, meta.steamAvatarUrl, meta.steam64Id
      - games: list of recent matches (without inline player stats)
    """
    return _get(f"/profile/id/{steam_id}", api_key=api_key)


def get_game_details(match_id: str, api_key: str = "") -> dict | None:
    """Fetch detailed stats for a single match."""
    return _get(f"/games/{match_id}", api_key=api_key)


def parse_player_info(profile: dict) -> dict:
    """Extract basic identity info from a Leetify profile response."""
    meta = profile.get("meta") or {}  # guard against explicit null in API response
    return {
        "steam_id": meta.get("steam64Id") or "",
        "username": meta.get("name") or "",
        "avatar_url": meta.get("steamAvatarUrl") or "",
    }


def parse_games(profile: dict) -> list[dict]:
    """Extract and normalise the list of games from a Leetify profile.

    Returns a list of dicts each containing:
      match_id, played_at, map_name, score_ct, score_t.
    Player stats are NOT included here – call get_game_details() and
    parse_game_player_stats() separately for each match.
    """
    games_raw = profile.get("games") or []
    parsed = []
    for g in games_raw:
        if not isinstance(g, dict):
            continue
        # Leetify stores scores as [own_team_score, enemy_team_score]
        scores = g.get("scores", [0, 0])

        # played_at may be an ISO string
        played_at_raw = g.get("gameFinishedAt") or g.get("gameCreatedAt")
        try:
            played_at = datetime.fromisoformat(played_at_raw.replace("Z", "+00:00")) if played_at_raw else None
        except (ValueError, AttributeError):
            played_at = None

        parsed.append(
            {
                "match_id": g.get("gameId", ""),
                "played_at": played_at,
                "map_name": g.get("mapName", ""),
                "score_ct": scores[0] if len(scores) > 0 else 0,
                "score_t": scores[1] if len(scores) > 1 else 0,
            }
        )
    return parsed


def parse_game_player_stats(game_details: dict) -> list[dict]:
    """Extract per-player stats from a game details API response.

    The /api/games/{matchId} endpoint returns a dict with a 'playerStats'
    list and a 'teams' list (used to compute total rounds for ADR).
    """
    player_stats_raw = game_details.get("playerStats") or []
    teams = game_details.get("teams") or []
    total_rounds = sum(t.get("score", 0) for t in teams if isinstance(t, dict)) if teams else 0
    return [_parse_player_game_stats(ps, total_rounds) for ps in player_stats_raw if isinstance(ps, dict)]


def _parse_player_game_stats(raw: dict, total_rounds: int = 0) -> dict:
    """Normalise a single player's in-game stats from Leetify's game details format."""
    kills = raw.get("totalKills", 0) or 0
    deaths = raw.get("totalDeaths", 0) or 0
    assists = raw.get("totalAssists", 0) or 0
    headshots = raw.get("shotsHitFoeHead", 0) or 0
    total_damage = float(raw.get("totalDamage", 0) or 0)
    adr = (total_damage / total_rounds) if total_rounds else 0.0

    return {
        "steam_id": raw.get("steam64Id", ""),
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "headshots": headshots,
        "adr": round(adr, 1),
        "rating": float(raw.get("personalPerformanceRating", 0) or 0),
        "leetify_rating": float(raw.get("leetifyRating", 0) or 0),
        "ct_rating": float(raw.get("ctLeetifyRating", 0) or 0),
        "t_rating": float(raw.get("tLeetifyRating", 0) or 0),
        "opening_kills": raw.get("openingKills", 0) or 0,
        "opening_deaths": raw.get("openingDeaths", 0) or 0,
        "utility_damage": float(raw.get("utilityDamage", 0) or 0),
    }
