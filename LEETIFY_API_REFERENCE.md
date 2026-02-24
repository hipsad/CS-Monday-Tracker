# Leetify Public CS API Reference

**Base URL:** `https://api-public.cs-prod.leetify.com`  
**Spec:** OAS 3.1  
**Docs / Developer Portal:** `https://leetify.com/app/developer`

---

## Authentication

All requests should include your API key via one of:
- `Authorization: Bearer <api_key>` header
- `_leetify_key: <api_key>` header

Unauthenticated requests are permitted but subject to stricter rate limits.

**Validate your key:**
```
GET /api-key/validate
Authorization: Bearer <api_key>
```

---

## Endpoints Used by This Application

### 1. Player Profile

```
GET /v3/profile?steam64_id=<steam64_id>
```

Returns the player's name, steam64_id, ranks, aggregate rating stats, and a `recent_matches` list.

**Key Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `steam64_id` | string | Player's Steam64 ID |
| `name` | string | Player's display name |
| `recent_matches` | array | List of recent match summaries (see Match Entry below) |

> **Note:** Avatar URLs are not included in the new public API. Use the Steam Web API for avatars.

---

### 2. Full Match History

```
GET /v3/profile/matches?steam64_id=<steam64_id>
```

Returns the complete match history for a player. Same schema as `recent_matches` from the profile endpoint.

**Response:** Array of Match Entry objects (or `{ matches: [...] }`).

---

### 3. Match Details

```
GET /v2/matches/<gameId>
```

Returns detailed per-player stats for a single match.

**Key Response Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Match ID |
| `stats` | array | List of per-player stat objects |
| `team_scores` | array | `[{team_number, score}]` – rounds won per team |

---

## Schema: Match Entry (from `/v3/profile` or `/v3/profile/matches`)

Each element in `recent_matches` contains the following fields for the **queried player**:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Match/game ID |
| `finished_at` | string (ISO 8601) | When the match ended |
| `map_name` | string | Map name (e.g. `de_mirage`) |
| `score` | array | `[own_team_score, enemy_team_score]` |
| `kills` | int | Total kills |
| `deaths` | int | Total deaths |
| `assists` | int | Total assists |
| `dpr` | float | Damage per round (ADR) |
| `hs_percent` | float | Headshot percentage (0–100) |
| `leetify_rating` | float | Leetify performance rating as a **fraction** (e.g. `-0.0196`) – multiply by 100 for display |
| `ct_leetify_rating` | float | Leetify rating on CT side (fraction, multiply ×100) |
| `t_leetify_rating` | float | Leetify rating on T side (fraction, multiply ×100) |

> **Important – Rating Scaling:**  
> The `leetify_rating` field is returned as a small fraction (e.g. `0.0234`).  
> Multiply by **100** to get the display value shown on Leetify (e.g. `2.34`).  
> A rating of `0` typically means no valid data was recorded for that game.

---

## Schema: Per-Player Stats (from `/v2/matches/<id>` → `stats[]`)

| Field | Type | Description |
|-------|------|-------------|
| `steam64_id` | string | Player's Steam64 ID |
| `total_kills` | int | Total kills |
| `total_deaths` | int | Total deaths |
| `total_assists` | int | Total assists |
| `total_hs_kills` | int | Headshot kill count |
| `hs_percent` | float | Headshot percentage |
| `dpr` | float | Damage per round (ADR) |
| `leetify_rating` | float | Leetify rating (fraction, multiply ×100) |
| `ct_leetify_rating` | float | CT side Leetify rating (fraction) |
| `t_leetify_rating` | float | T side Leetify rating (fraction) |

---

## Notes on Data Quality

- Games synced **before February 5, 2026** may have `adr = 0` and `leetify_rating = 0` because the earlier API responses lacked these fields or the mapping was not yet implemented.
- The application's averaging functions **exclude zero-value games** from ADR and rating calculations to avoid skewing averages with incomplete data.
- `rating` and `leetify_rating` in the database both reflect the Leetify performance metric. The legacy `personalPerformanceRating` (HLTV 2.0-style) is not available in the new public API.

---

## Steam Web API (for Avatars)

The Leetify public API does not return avatar URLs. Use the Steam Web API:

```
GET https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/
    ?key=<STEAM_API_KEY>&steamids=<steam64_id1>,<steam64_id2>,...
```

**Response fields used:** `personaname` (username), `avatarfull` (avatar URL).

---

## Rate Limits

- **Authenticated:** Standard limits apply per the Leetify Developer Guidelines.
- **Unauthenticated:** Increased rate limiting.
- Configure your API key at: `https://leetify.com/app/developer`
