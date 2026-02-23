"""Leetify API client for fetching CS player and match data."""
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

LEETIFY_API_BASE = "https://api.leetify.com/api"


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
      - name, steamAvatarUrl
      - games: list of recent matches with per-player stats
      - appRatings: cumulative skill ratings
    """
    return _get(f"/profile/{steam_id}", api_key=api_key)


def get_game_details(match_id: str, api_key: str = "") -> dict | None:
    """Fetch detailed stats for a single match."""
    return _get(f"/games/{match_id}", api_key=api_key)


def parse_player_info(profile: dict) -> dict:
    """Extract basic identity info from a Leetify profile response."""
    return {
        "steam_id": profile.get("steamId64", ""),
        "username": profile.get("name", "Unknown"),
        "avatar_url": profile.get("steamAvatarUrl", ""),
    }


def parse_games(profile: dict) -> list[dict]:
    """Extract and normalise the list of games from a Leetify profile.

    Returns a list of dicts each containing:
      match_id, played_at, map_name, score_ct, score_t, and
      player_stats (list of per-player stat dicts).
    """
    games_raw = profile.get("games", [])
    parsed = []
    for g in games_raw:
        # Leetify stores team scores as a list [ct_score, t_score]
        scores = g.get("scores", [0, 0])

        # played_at may be an ISO string
        played_at_raw = g.get("gameFinishedAt") or g.get("gameCreatedAt")
        try:
            played_at = datetime.fromisoformat(played_at_raw.replace("Z", "+00:00")) if played_at_raw else None
        except (ValueError, AttributeError):
            played_at = None

        player_stats = []
        for player_raw in g.get("playerStats", []):
            player_stats.append(_parse_player_game_stats(player_raw))

        parsed.append(
            {
                "match_id": g.get("gameId", ""),
                "played_at": played_at,
                "map_name": g.get("mapName", ""),
                "score_ct": scores[0] if len(scores) > 0 else 0,
                "score_t": scores[1] if len(scores) > 1 else 0,
                "player_stats": player_stats,
            }
        )
    return parsed


def _parse_player_game_stats(raw: dict) -> dict:
    """Normalise a single player's in-game stats from Leetify's format."""
    # Leetify nests some fields under subkeys
    aim = raw.get("aim", {}) or {}
    positioning = raw.get("positioning", {}) or {}
    utility = raw.get("utility", {}) or {}
    opening = raw.get("opening", {}) or {}

    kills = raw.get("kills", 0) or 0
    deaths = raw.get("deaths", 0) or 0
    headshots = raw.get("hs", 0) or 0

    return {
        "steam_id": raw.get("steamId64", ""),
        "kills": kills,
        "deaths": deaths,
        "assists": raw.get("assists", 0) or 0,
        "headshots": headshots,
        "adr": float(raw.get("adr", 0) or 0),
        "rating": float(raw.get("hltvRatingOverall", 0) or raw.get("hltvRating2Overall", 0) or 0),
        "leetify_rating": float(raw.get("leetifyRatingOverall", 0) or 0),
        "ct_rating": float(raw.get("hltvRatingCt", 0) or raw.get("hltvRating2Ct", 0) or 0),
        "t_rating": float(raw.get("hltvRatingT", 0) or raw.get("hltvRating2T", 0) or 0),
        "opening_kills": opening.get("attempts", 0) or raw.get("openingKills", 0) or 0,
        "opening_deaths": opening.get("deaths", 0) or raw.get("openingDeaths", 0) or 0,
        "utility_damage": float(utility.get("utilityDamage", 0) or raw.get("utilityDamageDealt", 0) or 0),
    }
