"""Leetify Public CS API client for fetching CS player and match data.

API base: https://api-public.cs-prod.leetify.com
Docs: https://api-public.cs-prod.leetify.com (OAS 3.1)

Key endpoints:
  GET /v3/profile?steam64_id=<id>          – player profile + recent_matches
  GET /v3/profile/matches?steam64_id=<id>  – full match history
  GET /v2/matches/<gameId>                 – per-match stats for all players
"""
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

LEETIFY_API_BASE = "https://api-public.cs-prod.leetify.com"


def _get(path: str, api_key: str = "", params: dict | None = None, timeout: int = 15) -> dict | list | None:
    """Make a GET request to the Leetify Public API and return parsed JSON."""
    url = f"{LEETIFY_API_BASE}{path}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        logger.error("Leetify HTTP error for %s: %s", url, exc)
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("Leetify request failed for %s: %s", url, exc)
        return None


def get_player_profile(steam_id: str, api_key: str = "") -> dict | None:
    """Fetch profile data for a player from their Steam64 ID.

    The public API endpoint (/v3/profile) returns the player's name,
    steam64_id, ranks, aggregate rating stats, and a recent_matches list.
    Avatar URLs are not included; use the Steam Web API for those.
    """
    return _get("/v3/profile", api_key=api_key, params={"steam64_id": steam_id})


def get_player_matches(steam_id: str, api_key: str = "") -> list[dict]:
    """Fetch the full match history for a player via /v3/profile/matches.

    Returns a list of match summary dicts (same schema as recent_matches in
    the profile response).  Falls back to an empty list on failure.
    """
    data = _get("/v3/profile/matches", api_key=api_key, params={"steam64_id": steam_id})
    if data is None:
        return []
    if isinstance(data, list):
        return data
    # The endpoint may wrap the list under a key
    return data.get("matches") or data.get("recent_matches") or []


def get_game_details(match_id: str, api_key: str = "") -> dict | None:
    """Fetch detailed stats for a single match via /v2/matches/{gameId}."""
    return _get(f"/v2/matches/{match_id}", api_key=api_key)


def parse_player_info(profile: dict) -> dict:
    """Extract basic identity info from a Leetify profile response.

    Supports both the new public API (top-level snake_case fields) and the
    legacy API (nested under 'meta' with camelCase fields).
    """
    # Legacy API: fields were nested under 'meta'
    meta = profile.get("meta") or {}
    return {
        "steam_id": profile.get("steam64_id") or meta.get("steam64Id") or "",
        "username": profile.get("name") or meta.get("name") or "",
        # New public API does not include avatar; fall back to legacy field
        "avatar_url": (
            profile.get("avatar_url")
            or profile.get("steamAvatarUrl")
            or meta.get("steamAvatarUrl")
            or ""
        ),
    }


def parse_games(profile: dict) -> list[dict]:
    """Extract and normalise the list of games from a Leetify profile.

    Returns a list of dicts each containing:
      match_id, played_at, map_name, score_ct, score_t.
    Player stats are NOT included here – call get_game_details() and
    parse_game_player_stats() separately for each match.

    Supports both:
      * New public API: 'recent_matches' with snake_case fields
        (id, finished_at, map_name, score)
      * Legacy API: 'games' with camelCase fields
        (gameId, gameFinishedAt, mapName, scores)
    """
    # New public API uses 'recent_matches'; legacy used 'games'
    games_raw = profile.get("recent_matches") or profile.get("games") or []
    parsed = []
    for g in games_raw:
        if not isinstance(g, dict):
            continue

        # score / scores: [own_team_score, enemy_team_score]
        scores = g.get("score") or g.get("scores") or [0, 0]

        # finished_at (new) / gameFinishedAt / gameCreatedAt (legacy)
        played_at_raw = (
            g.get("finished_at")
            or g.get("gameFinishedAt")
            or g.get("gameCreatedAt")
        )
        try:
            played_at = (
                datetime.fromisoformat(played_at_raw.replace("Z", "+00:00"))
                if played_at_raw
                else None
            )
        except (ValueError, AttributeError):
            played_at = None

        parsed.append(
            {
                # id (new) / gameId (legacy)
                "match_id": g.get("id") or g.get("gameId") or "",
                "played_at": played_at,
                # map_name (new) / mapName (legacy)
                "map_name": g.get("map_name") or g.get("mapName") or "",
                "score_ct": scores[0] if len(scores) > 0 else 0,
                "score_t": scores[1] if len(scores) > 1 else 0,
            }
        )
    return parsed


def parse_game_player_stats(game_details: dict) -> list[dict]:
    """Extract per-player stats from a game details API response.

    Supports both:
      * New public API (/v2/matches/{id}):
        - player list under 'stats' key
        - round totals under 'team_scores': [{'team_number': N, 'score': N}]
      * Legacy API (/api/games/{id}):
        - player list under 'playerStats' key
        - round totals under 'teams': [{'score': N}] or 'teamScores': [N, N]

    When no game-level round count can be determined, each player's
    individual round breakdown (rounds_count / tRoundsWon + ctRoundsWon +
    tRoundsLost + ctRoundsLost) is used as a per-player fallback.
    """
    # New public API uses 'stats'; legacy used 'playerStats'
    player_stats_raw = (
        game_details.get("stats") or game_details.get("playerStats") or []
    )

    # Derive total rounds for ADR calculation
    total_rounds = 0
    # New API: team_scores is a list of {team_number, score} objects
    team_scores_obj = game_details.get("team_scores") or []
    if team_scores_obj:
        total_rounds = sum(
            t.get("score", 0) for t in team_scores_obj if isinstance(t, dict)
        )
    else:
        # Legacy: teams list with score, or flat teamScores array
        teams = game_details.get("teams") or []
        if teams:
            total_rounds = sum(
                t.get("score", 0) for t in teams if isinstance(t, dict)
            )
        else:
            flat = game_details.get("teamScores") or []
            if flat:
                total_rounds = sum(int(s) for s in flat if s is not None)

    return [
        _parse_player_game_stats(ps, total_rounds)
        for ps in player_stats_raw
        if isinstance(ps, dict)
    ]


def _parse_player_game_stats(raw: dict, total_rounds: int = 0) -> dict:
    """Normalise a single player's in-game stats.

    Supports both the new public API (snake_case) and the legacy API
    (camelCase) so that existing tests and any cached data continue to work.
    """
    # ---- Core counts: prefer snake_case (new API), fall back to camelCase ----
    kills   = raw.get("total_kills")   if raw.get("total_kills")   is not None else (raw.get("totalKills",   0) or 0)
    deaths  = raw.get("total_deaths")  if raw.get("total_deaths")  is not None else (raw.get("totalDeaths",  0) or 0)
    assists = raw.get("total_assists") if raw.get("total_assists") is not None else (raw.get("totalAssists", 0) or 0)
    kills   = kills   or 0
    deaths  = deaths  or 0
    assists = assists or 0

    # ---- Headshot kills ----
    # New API: total_hs_kills (headshot kills count, the right metric for HS%)
    # Legacy API: shotsHitFoeHead (shots that hit enemy head – used as proxy)
    headshots = (
        raw.get("total_hs_kills")
        if raw.get("total_hs_kills") is not None
        else (raw.get("shotsHitFoeHead", 0) or 0)
    )
    headshots = headshots or 0

    # ---- ADR ----
    # New API provides dpr (damage per round) pre-computed – use it directly.
    # Legacy API requires computing from totalDamage / total_rounds.
    dpr_val = raw.get("dpr")
    if dpr_val is not None:
        adr = round(float(dpr_val), 1)
    else:
        total_damage = float(
            raw.get("total_damage") if raw.get("total_damage") is not None
            else (raw.get("totalDamage", 0) or 0)
        )
        # Per-player fallback when game-level round count is unavailable
        if not total_rounds:
            total_rounds = (
                (raw.get("rounds_count") or 0)
                or (
                    (raw.get("tRoundsWon") or 0)
                    + (raw.get("ctRoundsWon") or 0)
                    + (raw.get("tRoundsLost") or 0)
                    + (raw.get("ctRoundsLost") or 0)
                )
            )
        adr = round(total_damage / total_rounds, 1) if total_rounds else 0.0

    # ---- Ratings ----
    # New API: leetify_rating per match (snake_case)
    # Legacy API: leetifyRating, personalPerformanceRating (camelCase)
    leetify_rating = float(
        raw.get("leetify_rating") if raw.get("leetify_rating") is not None
        else (raw.get("leetifyRating", 0) or 0)
    )
    # personalPerformanceRating was the HLTV-style metric in the old API.
    # The new public API does not expose a separate HLTV 2.0 value, so we
    # fall back to leetify_rating as the best available performance proxy.
    rating = float(
        raw.get("personalPerformanceRating") or leetify_rating or 0
    )
    ct_rating = float(
        raw.get("ct_leetify_rating") if raw.get("ct_leetify_rating") is not None
        else (raw.get("ctLeetifyRating", 0) or 0)
    )
    t_rating = float(
        raw.get("t_leetify_rating") if raw.get("t_leetify_rating") is not None
        else (raw.get("tLeetifyRating", 0) or 0)
    )

    # ---- Fields absent from the new public API ----
    opening_kills  = raw.get("openingKills",  0) or 0
    opening_deaths = raw.get("openingDeaths", 0) or 0
    utility_damage = float(raw.get("utilityDamage", 0) or 0)

    return {
        # steam64_id (new) / steam64Id (legacy)
        "steam_id": raw.get("steam64_id") or raw.get("steam64Id") or "",
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "headshots": headshots,
        "adr": adr,
        "rating": rating,
        "leetify_rating": leetify_rating,
        "ct_rating": ct_rating,
        "t_rating": t_rating,
        "opening_kills": opening_kills,
        "opening_deaths": opening_deaths,
        "utility_damage": utility_damage,
    }
