"""Steam Web API client for fetching player profiles and friend lists."""
import logging

import requests

logger = logging.getLogger(__name__)

STEAM_API_BASE = "https://api.steampowered.com"


def _get(path: str, params: dict, timeout: int = 15) -> dict | None:
    """Make a GET request to the Steam Web API and return parsed JSON."""
    url = f"{STEAM_API_BASE}{path}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as exc:
        logger.error("Steam API HTTP error for %s: %s", url, exc)
        return None
    except requests.exceptions.RequestException as exc:
        logger.error("Steam API request failed for %s: %s", url, exc)
        return None


def get_friend_list(steam_id: str, api_key: str = "") -> list[str] | None:
    """Return a list of Steam64 IDs for the given player's friends.

    Returns None if the request fails (e.g. private profile, bad key).
    """
    data = _get(
        "/ISteamUser/GetFriendList/v0001/",
        params={"key": api_key, "steamid": steam_id, "relationship": "friend"},
    )
    if data is None:
        return None
    friends = data.get("friendslist", {}).get("friends", [])
    return [f["steamid"] for f in friends]


def get_player_summaries(steam_ids: list[str], api_key: str = "") -> list[dict]:
    """Return profile summaries for up to 100 Steam IDs at once."""
    if not steam_ids:
        return []
    data = _get(
        "/ISteamUser/GetPlayerSummaries/v0002/",
        params={"key": api_key, "steamids": ",".join(steam_ids[:100])},
    )
    if data is None:
        return []
    players = data.get("response", {}).get("players", [])
    return [_parse_summary(p) for p in players]


def _parse_summary(raw: dict) -> dict:
    """Normalise a single player summary from Steam's format."""
    return {
        "steam_id": raw.get("steamid", ""),
        "username": raw.get("personaname", "Unknown"),
        "avatar_url": raw.get("avatarmedium") or raw.get("avatar", ""),
        "profile_url": raw.get("profileurl", ""),
        "real_name": raw.get("realname", ""),
    }
