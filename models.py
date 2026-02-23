"""Database models for the CS Monday Tracker."""
from datetime import datetime, timezone
from extensions import db


# Association table for session <-> player many-to-many
session_players = db.Table(
    "session_players",
    db.Column("session_id", db.Integer, db.ForeignKey("session.id"), primary_key=True),
    db.Column("player_id", db.Integer, db.ForeignKey("player.id"), primary_key=True),
)


class Player(db.Model):
    """A tracked CS player identified by their Steam64 ID."""

    id = db.Column(db.Integer, primary_key=True)
    steam_id = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(100))
    avatar_url = db.Column(db.String(500))
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    games = db.relationship("PlayerGame", back_populates="player", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "steam_id": self.steam_id,
            "username": self.username,
            "avatar_url": self.avatar_url,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


class Game(db.Model):
    """A single CS match fetched from Leetify."""

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.String(100), unique=True, nullable=False)
    played_at = db.Column(db.DateTime)
    map_name = db.Column(db.String(50))
    score_ct = db.Column(db.Integer, default=0)
    score_t = db.Column(db.Integer, default=0)
    session_id = db.Column(db.Integer, db.ForeignKey("session.id"), nullable=True)

    player_games = db.relationship("PlayerGame", back_populates="game", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "played_at": self.played_at.isoformat() if self.played_at else None,
            "map_name": self.map_name,
            "score_ct": self.score_ct,
            "score_t": self.score_t,
            "session_id": self.session_id,
        }


class PlayerGame(db.Model):
    """Per-player statistics for a single match."""

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)

    # Core stats
    kills = db.Column(db.Integer, default=0)
    deaths = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    headshots = db.Column(db.Integer, default=0)
    adr = db.Column(db.Float, default=0.0)       # Average Damage per Round
    rating = db.Column(db.Float, default=0.0)    # Leetify rating (HLTV-style)
    leetify_rating = db.Column(db.Float, default=0.0)
    ct_rating = db.Column(db.Float, default=0.0)
    t_rating = db.Column(db.Float, default=0.0)
    opening_kills = db.Column(db.Integer, default=0)
    opening_deaths = db.Column(db.Integer, default=0)
    utility_damage = db.Column(db.Float, default=0.0)

    player = db.relationship("Player", back_populates="games")
    game = db.relationship("Game", back_populates="player_games")

    @property
    def kd_ratio(self):
        return round(self.kills / max(self.deaths, 1), 2)

    @property
    def headshot_pct(self):
        return round((self.headshots / max(self.kills, 1)) * 100, 1)

    def to_dict(self):
        return {
            "id": self.id,
            "player_id": self.player_id,
            "game_id": self.game_id,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "headshots": self.headshots,
            "kd_ratio": self.kd_ratio,
            "headshot_pct": self.headshot_pct,
            "adr": self.adr,
            "rating": self.rating,
            "leetify_rating": self.leetify_rating,
            "ct_rating": self.ct_rating,
            "t_rating": self.t_rating,
            "opening_kills": self.opening_kills,
            "opening_deaths": self.opening_deaths,
            "utility_damage": self.utility_damage,
        }


class Session(db.Model):
    """A Monday gaming session grouping multiple games."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text)

    players = db.relationship("Player", secondary=session_players, backref="sessions")
    games = db.relationship("Game", backref="session")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "notes": self.notes,
            "player_count": len(self.players),
            "game_count": len(self.games),
        }


class AIAnalysis(db.Model):
    """Stored AI analysis results."""

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    scope = db.Column(db.String(50))     # "session", "all_time", "player"
    scope_id = db.Column(db.String(50))  # session id or steam_id
    prompt_summary = db.Column(db.Text)
    analysis = db.Column(db.Text)
    model_used = db.Column(db.String(50))

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "prompt_summary": self.prompt_summary,
            "analysis": self.analysis,
            "model_used": self.model_used,
        }
