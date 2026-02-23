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
      match_id, played_at, map_name, score_ct, score_t, own_stats.
    own_stats is a dict of the queried player's own per-match stats when the
    profile endpoint embeds them (ADR, HS%, rating, etc.), or None otherwise.
    Call get_game_details() and parse_game_player_stats() separately to obtain
    stats for all other players in each match.

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
                # Per-player stats embedded by the profile endpoint for the
                # queried player.  None when not present (e.g. legacy games
                # list or a bare match-history entry with no stat fields).
                "own_stats": _extract_own_stats_from_match_entry(g),
            }
        )
    return parsed


def _extract_own_stats_from_match_entry(g: dict) -> dict | None:
    """Extract the queried player's own stats from a profile match-list entry.

    The /v3/profile and /v3/profile/matches endpoints embed per-player stats
    directly in each match entry for the queried player.  Field names follow
    the new public API convention (snake_case), with HS% expressed as a
    percentage value (0–100) and leetify_rating as a small fraction that is
    scaled ×100 to match Leetify's display range.

    Returns None when no per-player stats are present (e.g. the entry only
    contains match metadata without any kill/death fields).
    """
    # 'kills' or 'total_kills' acts as a signal that stats are embedded.
    kills_raw = g.get("kills") if g.get("kills") is not None else g.get("total_kills")
    if kills_raw is None:
        return None

    kills = int(kills_raw)
    deaths_raw = g.get("deaths") if g.get("deaths") is not None else g.get("total_deaths")
    deaths = int(deaths_raw) if deaths_raw is not None else 0
    assists_raw = g.get("assists") if g.get("assists") is not None else g.get("total_assists")
    assists = int(assists_raw) if assists_raw is not None else 0

    # ADR: pre-computed 'dpr' or 'adr' (both represent damage per round)
    adr_raw = g.get("dpr") if g.get("dpr") is not None else g.get("adr")
    adr = round(float(adr_raw), 1) if adr_raw is not None else 0.0

    # Headshots: percentage-based field ('hs_percent' / 'hsp') or kill count
    hs_pct = g.get("hs_percent") if g.get("hs_percent") is not None else g.get("hsp")
    if hs_pct is not None:
        headshots = round(float(hs_pct) / 100 * max(kills, 1))
    else:
        hs_raw = (
            g.get("total_hs_kills")
            if g.get("total_hs_kills") is not None
            else g.get("hs_kills")
        )
        headshots = int(hs_raw) if hs_raw is not None else 0

    # Ratings: new API returns fractions (e.g. -0.0196) → scale ×100 to get
    # Leetify's display value (e.g. -1.96).  Legacy camelCase fields are
    # already in the correct range and are used as-is.
    lr_new = g.get("leetify_rating")
    lr_legacy = g.get("leetifyRating")
    if lr_new is not None:
        leetify_rating = round(float(lr_new) * 100, 2)
    elif lr_legacy is not None:
        leetify_rating = float(lr_legacy)
    else:
        leetify_rating = 0.0

    ct_lr_new = g.get("ct_leetify_rating")
    ct_lr_legacy = g.get("ctLeetifyRating")
    ct_rating = (
        round(float(ct_lr_new) * 100, 2) if ct_lr_new is not None
        else float(ct_lr_legacy or 0)
    )

    t_lr_new = g.get("t_leetify_rating")
    t_lr_legacy = g.get("tLeetifyRating")
    t_rating = (
        round(float(t_lr_new) * 100, 2) if t_lr_new is not None
        else float(t_lr_legacy or 0)
    )

    # HLTV-style rating: use personalPerformanceRating when available
    # (legacy only); otherwise fall back to the scaled leetify_rating.
    rating = float(g.get("personalPerformanceRating") or leetify_rating or 0)

    return {
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "headshots": headshots,
        "adr": adr,
        "rating": rating,
        "leetify_rating": leetify_rating,
        "ct_rating": ct_rating,
        "t_rating": t_rating,
        "opening_kills": int(g.get("openingKills") or 0),
        "opening_deaths": int(g.get("openingDeaths") or 0),
        "utility_damage": float(g.get("utilityDamage") or 0),
    }


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

    def _field(new_key: str, legacy_key: str, default: int | float = 0) -> int | float:
        """Return the value for a stat field, preferring the new API key."""
        v = raw.get(new_key)
        return v if v is not None else (raw.get(legacy_key) or default)

    # ---- Core counts ----
    kills     = int(_field("total_kills",   "totalKills",   0))
    deaths    = int(_field("total_deaths",  "totalDeaths",  0))
    assists   = int(_field("total_assists", "totalAssists", 0))

    # ---- Headshot kills ----
    # New API: total_hs_kills (headshot kills count) or hs_percent (percentage)
    # Legacy API: shotsHitFoeHead (shots that hit enemy head – used as proxy)
    hs_pct_val = (
        raw.get("hs_percent") if raw.get("hs_percent") is not None
        else raw.get("hsp")
    )
    if hs_pct_val is not None:
        # Convert percentage to approximate headshot kill count
        headshots = round(float(hs_pct_val) / 100 * max(kills, 1))
    else:
        headshots = int(_field("total_hs_kills", "shotsHitFoeHead", 0))

    # ---- ADR ----
    # New API provides dpr or adr (damage per round) pre-computed – use directly.
    # Legacy API requires computing from totalDamage / total_rounds.
    dpr_val = raw.get("dpr") if raw.get("dpr") is not None else raw.get("adr")
    if dpr_val is not None:
        adr = round(float(dpr_val), 1)
    else:
        total_damage = float(_field("total_damage", "totalDamage", 0))
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
    # New API: leetify_rating per match (snake_case) returned as a small
    # fraction (e.g. -0.0196).  Multiply by 100 to get the display value
    # shown on Leetify (e.g. -1.96).
    # Legacy API: leetifyRating is already in the correct display range.
    lr_new = raw.get("leetify_rating")
    lr_legacy = raw.get("leetifyRating")
    if lr_new is not None:
        leetify_rating = round(float(lr_new) * 100, 2)
    elif lr_legacy is not None:
        leetify_rating = float(lr_legacy)
    else:
        leetify_rating = 0.0

    ct_lr_new = raw.get("ct_leetify_rating")
    ct_lr_legacy = raw.get("ctLeetifyRating")
    ct_rating = (
        round(float(ct_lr_new) * 100, 2) if ct_lr_new is not None
        else float(ct_lr_legacy or 0)
    )

    t_lr_new = raw.get("t_leetify_rating")
    t_lr_legacy = raw.get("tLeetifyRating")
    t_rating = (
        round(float(t_lr_new) * 100, 2) if t_lr_new is not None
        else float(t_lr_legacy or 0)
    )

    # personalPerformanceRating was the HLTV-style metric in the old API.
    # The new public API does not expose a separate HLTV 2.0 value, so we
    # fall back to leetify_rating (already scaled) as the best available proxy.
    rating = float(raw.get("personalPerformanceRating") or leetify_rating or 0)

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
