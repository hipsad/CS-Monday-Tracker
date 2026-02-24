"""OpenAI integration for CS performance analysis."""
import json
import logging

logger = logging.getLogger(__name__)


def _build_stats_summary(player_stats_list: list[dict], per_game_data: dict | None = None) -> str:
    """Convert a list of player aggregate stats into a readable text block."""
    lines = []
    for p in player_stats_list:
        line = (
            f"- {p['username']} | Games: {p['games']} | Avg Rating: {p['avg_leetify_rating']:.2f} | "
            f"Avg K/D: {p['avg_kd']:.2f} | Avg ADR: {p['avg_adr']:.1f} | "
            f"Avg HS%: {p['avg_hs_pct']:.1f}% | Win Rate: {p.get('win_rate', 0):.1f}%"
        )
        lines.append(line)
        if per_game_data and p["steam_id"] in per_game_data:
            games = per_game_data[p["steam_id"]][:5]  # show up to 5 recent games
            for g in games:
                lines.append(
                    f"  Recent game: K={g.get('kills',0)} D={g.get('deaths',0)} "
                    f"ADR={g.get('adr',0):.1f} Rating={g.get('leetify_rating',0):.2f}"
                )
    return "\n".join(lines)


def generate_analysis(
    player_stats_list: list[dict],
    scope: str,
    openai_api_key: str,
    per_game_data: dict | None = None,
) -> str:
    """Ask OpenAI to analyse player stats and identify strengths, weaknesses, and strategies.

    Args:
        player_stats_list: List of aggregate stat dicts for each player.
        scope: Human-readable label like "this session" or "all time".
        openai_api_key: OpenAI API key.
        per_game_data: Optional dict mapping steam_id → list of recent game dicts.

    Returns:
        The AI-generated analysis text, or an error message.
    """
    if not openai_api_key:
        return "OpenAI API key is not configured. Add OPENAI_API_KEY to your .env file."

    try:
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI(api_key=openai_api_key)
    except ImportError:
        return "openai package is not installed. Run: pip install openai"

    stats_text = _build_stats_summary(player_stats_list, per_game_data)
    player_names = ", ".join(p["username"] for p in player_stats_list)

    prompt = (
        f"You are a Counter-Strike performance coach analysing stats for a friend group.\n"
        f"Players: {player_names}\n\n"
        f"Stats ({scope}):\n{stats_text}\n\n"
        f"For each player, please provide:\n"
        f"1. **Strengths** – what they do well based on the numbers.\n"
        f"2. **Weaknesses** – specific areas where performance is below average.\n"
        f"3. **Recommended Strategies** – concrete, actionable in-game tips tailored to their stats.\n\n"
        f"After the individual breakdown, add:\n"
        f"4. **Team Overview** – overall team strengths/weaknesses and a suggested team strategy.\n\n"
        f"Keep the tone friendly, honest, and specific to the numbers provided."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful CS2/CSGO performance analyst."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        from openai import OpenAIError
        if isinstance(exc, OpenAIError):
            logger.error("OpenAI API error: %s", exc)
            return f"AI analysis failed: {exc}"
        raise
