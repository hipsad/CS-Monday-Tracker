"""OpenAI integration for CS performance analysis."""
import json
import logging

logger = logging.getLogger(__name__)


def _build_stats_summary(player_stats_list: list[dict]) -> str:
    """Convert a list of player aggregate stats into a readable text block."""
    lines = []
    for p in player_stats_list:
        lines.append(
            f"- {p['username']} | Games: {p['games']} | Avg Rating: {p['avg_rating']:.2f} | "
            f"Avg K/D: {p['avg_kd']:.2f} | Avg ADR: {p['avg_adr']:.1f} | "
            f"Avg HS%: {p['avg_hs_pct']:.1f}% | Win Rate: {p.get('win_rate', 0):.1f}%"
        )
    return "\n".join(lines)


def generate_analysis(player_stats_list: list[dict], scope: str, openai_api_key: str) -> str:
    """Ask OpenAI to analyse player stats and identify problem areas.

    Args:
        player_stats_list: List of aggregate stat dicts for each player.
        scope: Human-readable label like "this session" or "all time".
        openai_api_key: OpenAI API key.

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

    stats_text = _build_stats_summary(player_stats_list)
    player_names = ", ".join(p["username"] for p in player_stats_list)

    prompt = (
        f"You are a Counter-Strike performance coach analysing stats for a friend group.\n"
        f"Players: {player_names}\n\n"
        f"Stats ({scope}):\n{stats_text}\n\n"
        f"Please provide:\n"
        f"1. An overall team performance summary.\n"
        f"2. The standout performer and why.\n"
        f"3. The player who needs the most improvement ('problem player') and specific areas to work on.\n"
        f"4. One concrete actionable tip for each player.\n"
        f"Keep your response concise and friendly but honest."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful CS2/CSGO performance analyst."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        from openai import OpenAIError
        if isinstance(exc, OpenAIError):
            logger.error("OpenAI API error: %s", exc)
            return f"AI analysis failed: {exc}"
        raise
