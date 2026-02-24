"""CS Monday Tracker – Flask application entry point."""
from flask import Flask, jsonify, request, render_template, abort
from flask_cors import CORS
from sqlalchemy import func

from config import Config
from extensions import db
import leetify as leetify_client
import openai_client
import steam as steam_client


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    CORS(app)
    db.init_app(app)

    with app.app_context():
        # Import models so SQLAlchemy registers them before create_all
        from models import Player, Game, PlayerGame, Session, AIAnalysis  # noqa: F401
        db.create_all()

    # ------------------------------------------------------------------ #
    # Frontend routes                                                       #
    # ------------------------------------------------------------------ #

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    # ------------------------------------------------------------------ #
    # Player management                                                     #
    # ------------------------------------------------------------------ #

    @app.route("/api/players", methods=["GET"])
    def list_players():
        from models import Player
        players = Player.query.order_by(Player.username).all()
        return jsonify([p.to_dict() for p in players])

    @app.route("/api/players", methods=["POST"])
    def add_player():
        from models import Player
        data = request.get_json(force=True) or {}
        steam_id = (data.get("steam_id") or "").strip()
        if not steam_id:
            return jsonify({"error": "steam_id is required"}), 400

        existing = Player.query.filter_by(steam_id=steam_id).first()
        if existing:
            return jsonify({"error": "Player already tracked", "player": existing.to_dict()}), 409

        # Fetch identity from Leetify
        profile = leetify_client.get_player_profile(steam_id, api_key=app.config["LEETIFY_API_KEY"])
        if not profile:
            # Fall back to Steam API for name/avatar when Leetify is unavailable
            username = steam_id
            avatar_url = ""
            if app.config["STEAM_API_KEY"]:
                steam_info = steam_client.get_player_summaries([steam_id], api_key=app.config["STEAM_API_KEY"])
                if steam_info:
                    username = steam_info[0]["username"] or steam_id
                    avatar_url = steam_info[0]["avatar_url"] or ""
            player = Player(steam_id=steam_id, username=username, avatar_url=avatar_url)
        else:
            info = leetify_client.parse_player_info(profile)
            username = info["username"]
            avatar_url = info["avatar_url"]
            if not username and app.config["STEAM_API_KEY"]:
                steam_info = steam_client.get_player_summaries([steam_id], api_key=app.config["STEAM_API_KEY"])
                if steam_info:
                    username = steam_info[0]["username"]
                    avatar_url = avatar_url or steam_info[0]["avatar_url"]
            player = Player(
                steam_id=steam_id,
                username=username or steam_id,
                avatar_url=avatar_url,
            )

        db.session.add(player)
        db.session.commit()
        return jsonify(player.to_dict()), 201

    @app.route("/api/players/<steam_id>", methods=["GET"])
    def get_player(steam_id):
        from models import Player
        player = Player.query.filter_by(steam_id=steam_id).first_or_404()
        return jsonify(player.to_dict())

    @app.route("/api/players/<steam_id>", methods=["DELETE"])
    def remove_player(steam_id):
        from models import Player
        player = Player.query.filter_by(steam_id=steam_id).first_or_404()
        db.session.delete(player)
        db.session.commit()
        return jsonify({"message": "Player removed"})

    # ------------------------------------------------------------------ #
    # Session management                                                    #
    # ------------------------------------------------------------------ #

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        from models import Session
        sessions = Session.query.order_by(Session.date.desc()).all()
        return jsonify([s.to_dict() for s in sessions])

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        from models import Session, Player
        data = request.get_json(force=True) or {}
        name = data.get("name") or "Monday Session"
        notes = data.get("notes") or ""
        steam_ids = data.get("steam_ids") or []

        session = Session(name=name, notes=notes)
        for sid in steam_ids:
            player = Player.query.filter_by(steam_id=sid).first()
            if player:
                session.players.append(player)

        db.session.add(session)
        db.session.commit()
        return jsonify(session.to_dict()), 201

    @app.route("/api/sessions/current", methods=["GET"])
    def current_session():
        from models import Session, PlayerGame, Player
        session = Session.query.order_by(Session.date.desc()).first()
        if not session:
            return jsonify({"session": None, "players": []})

        stats = _aggregate_session_stats(session)
        return jsonify({"session": session.to_dict(), "players": stats})

    @app.route("/api/sessions/<int:session_id>", methods=["GET"])
    def get_session(session_id):
        from models import Session
        session = Session.query.get_or_404(session_id)
        stats = _aggregate_session_stats(session)
        return jsonify({"session": session.to_dict(), "players": stats})

    # ------------------------------------------------------------------ #
    # Sync – pull fresh data from Leetify for all tracked players          #
    # ------------------------------------------------------------------ #

    @app.route("/api/sync", methods=["POST"])
    def sync_players():
        """Fetch latest games from Leetify for all tracked players and upsert into DB."""
        from datetime import datetime, date, timezone
        from models import Player, Game, PlayerGame, Session
        data = request.get_json(force=True) or {}
        session_id = data.get("session_id")  # optional: attach games to a session

        players = Player.query.all()
        if not players:
            return jsonify({"message": "No players tracked yet. Add players first."}), 200

        # Auto-create a session for today if no session_id provided
        if not session_id:
            today = date.today()
            existing_session = Session.query.filter(
                func.date(Session.date) == today
            ).first()
            if existing_session:
                session_id = existing_session.id
            else:
                auto_session = Session(
                    name=f"Session – {today.strftime('%B %d, %Y')}",
                    notes="Auto-created by sync",
                )
                for player in players:
                    auto_session.players.append(player)
                db.session.add(auto_session)
                db.session.flush()
                session_id = auto_session.id

        synced_games = 0
        errors = []

        for player in players:
            profile = leetify_client.get_player_profile(player.steam_id, api_key=app.config["LEETIFY_API_KEY"])
            if not profile:
                errors.append(f"Could not fetch data for {player.username} ({player.steam_id})")
                continue

            # Update player identity
            info = leetify_client.parse_player_info(profile)
            username = info["username"]
            avatar_url = info["avatar_url"]
            if not username and app.config["STEAM_API_KEY"]:
                steam_info = steam_client.get_player_summaries([player.steam_id], api_key=app.config["STEAM_API_KEY"])
                if steam_info:
                    username = steam_info[0]["username"]
                    avatar_url = avatar_url or steam_info[0]["avatar_url"]
            player.username = username or player.username
            player.avatar_url = avatar_url or player.avatar_url

            # Try the dedicated match-history endpoint for a complete list;
            # fall back to the recent_matches included in the profile.
            match_list = leetify_client.get_player_matches(
                player.steam_id, api_key=app.config["LEETIFY_API_KEY"]
            )
            if not match_list:
                match_list = profile.get("recent_matches") or profile.get("games") or []

            # Build a synthetic profile-like dict so parse_games can normalise
            # the list regardless of which endpoint provided it.
            parsed_games = leetify_client.parse_games({"recent_matches": match_list})
            for g_data in parsed_games:
                match_id = g_data["match_id"]
                if not match_id:
                    continue

                # Fetch per-player stats from the game details endpoint
                game_details = leetify_client.get_game_details(match_id, api_key=app.config["LEETIFY_API_KEY"])
                if not game_details:
                    continue

                all_player_stats = leetify_client.parse_game_player_stats(game_details)

                # Upsert game record
                game = Game.query.filter_by(match_id=match_id).first()
                if not game:
                    game = Game(
                        match_id=match_id,
                        played_at=g_data["played_at"],
                        map_name=g_data["map_name"],
                        score_ct=g_data["score_ct"],
                        score_t=g_data["score_t"],
                        session_id=session_id,
                    )
                    db.session.add(game)
                    db.session.flush()  # get game.id
                    synced_games += 1

                # Build a lookup from steam_id → stats for all players in the game
                stats_by_steam_id = {s["steam_id"]: s for s in all_player_stats if s.get("steam_id")}

                def _upsert_player_game(p, ps):
                    pg = PlayerGame.query.filter_by(player_id=p.id, game_id=game.id).first()
                    if not pg:
                        pg = PlayerGame(player_id=p.id, game_id=game.id)
                        db.session.add(pg)
                    pg.kills = ps["kills"]
                    pg.deaths = ps["deaths"]
                    pg.assists = ps["assists"]
                    pg.headshots = ps["headshots"]
                    pg.adr = ps["adr"]
                    pg.rating = ps["rating"]
                    pg.leetify_rating = ps["leetify_rating"]
                    pg.ct_rating = ps["ct_rating"]
                    pg.t_rating = ps["t_rating"]
                    pg.opening_kills = ps["opening_kills"]
                    pg.opening_deaths = ps["opening_deaths"]
                    pg.utility_damage = ps["utility_damage"]
                    pg.raw_stats = ps.get("raw_stats")

                # Save stats for the current player.
                # Prefer own_stats from the profile match entry (contains ADR,
                # HS%, and correct assists) over the game-details response
                # which may omit those fields in the public API.
                own_stats = g_data.get("own_stats")
                player_stats = stats_by_steam_id.get(player.steam_id)
                if own_stats is not None:
                    _upsert_player_game(player, own_stats)
                elif player_stats is not None:
                    _upsert_player_game(player, player_stats)
                else:
                    # Player not found in this game – skip but still check friends
                    pass

                # Also save stats for any other tracked players found in this
                # game – this covers friends who may not have their own Leetify
                # profile accessible via the API.
                for other_player in players:
                    if other_player.steam_id == player.steam_id:
                        continue
                    other_stats = stats_by_steam_id.get(other_player.steam_id)
                    if other_stats:
                        _upsert_player_game(other_player, other_stats)

        db.session.commit()
        return jsonify({"synced_games": synced_games, "errors": errors})

    # ------------------------------------------------------------------ #
    # Stats API                                                             #
    # ------------------------------------------------------------------ #

    @app.route("/api/stats", methods=["GET"])
    def all_time_stats():
        """Aggregate stats for all players across all games."""
        from models import Player
        players = Player.query.all()
        stats = [_aggregate_player_stats(p) for p in players]
        # Sort by avg_rating descending so best player is first
        stats.sort(key=lambda x: x["avg_rating"], reverse=True)
        return jsonify(stats)

    @app.route("/api/stats/monthly", methods=["GET"])
    def monthly_stats():
        """Aggregate stats for all players over their last 15 games."""
        from models import Player, PlayerGame, Game
        players = Player.query.all()
        result = []
        for player in players:
            pgs = (
                PlayerGame.query
                .join(PlayerGame.game)
                .filter(PlayerGame.player_id == player.id)
                .order_by(Game.played_at.desc())
                .limit(15)
                .all()
            )
            if not pgs:
                result.append({
                    "steam_id": player.steam_id,
                    "username": player.username,
                    "avatar_url": player.avatar_url,
                    "games": 0,
                    "avg_rating": 0.0,
                    "avg_kd": 0.0,
                    "avg_adr": 0.0,
                    "avg_hs_pct": 0.0,
                    "avg_leetify_rating": 0.0,
                    "win_rate": 0.0,
                    "total_kills": 0,
                    "total_deaths": 0,
                    "total_assists": 0,
                })
                continue
            n = len(pgs)
            total_kills = sum(pg.kills for pg in pgs)
            total_deaths = sum(pg.deaths for pg in pgs)
            rated = [pg for pg in pgs if pg.leetify_rating != 0]
            adr_games = [pg for pg in pgs if pg.adr > 0]
            result.append({
                "steam_id": player.steam_id,
                "username": player.username,
                "avatar_url": player.avatar_url,
                "games": n,
                "avg_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
                "avg_leetify_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
                "avg_kd": round(total_kills / max(total_deaths, 1), 2),
                "avg_adr": round(sum(pg.adr for pg in adr_games) / len(adr_games), 1) if adr_games else 0.0,
                "avg_hs_pct": round(sum(pg.headshot_pct for pg in pgs) / n, 1),
                "win_rate": 0.0,
                "total_kills": total_kills,
                "total_deaths": total_deaths,
                "total_assists": sum(pg.assists for pg in pgs),
            })
        result.sort(key=lambda x: x["avg_rating"], reverse=True)
        return jsonify(result)

    @app.route("/api/stats/<steam_id>", methods=["GET"])
    def player_stats(steam_id):
        """Detailed stats for a single player including per-game breakdown."""
        from models import Player, PlayerGame, Game
        player = Player.query.filter_by(steam_id=steam_id).first_or_404()
        agg = _aggregate_player_stats(player)
        pgs = (
            PlayerGame.query
            .join(PlayerGame.game)
            .filter(PlayerGame.player_id == player.id)
            .order_by(Game.played_at.desc())
            .limit(15)
            .all()
        )
        games = []
        for pg in pgs:
            entry = pg.to_dict()
            entry["game"] = pg.game.to_dict()
            games.append(entry)
        return jsonify({"player": player.to_dict(), "stats": agg, "games": games})

    @app.route("/api/stats/records", methods=["GET"])
    def stat_records():
        """Return single-game record holders from the beginning of the current year."""
        from datetime import datetime, timezone, date
        from models import PlayerGame, Game
        from sqlalchemy import desc
        year_start = datetime(date.today().year, 1, 1, tzinfo=timezone.utc)
        records = {}
        # (result_key, ORM column/property, display label)
        # For @property fields (kd_ratio, headshot_pct) we must do a Python sort;
        # for plain columns we let the DB do the ordering.
        column_categories = [
            ("best_rating",      PlayerGame.leetify_rating,  "Best Rating"),
            ("best_adr",         PlayerGame.adr,             "ADR"),
            ("most_kills",       PlayerGame.kills,           "Kills"),
            ("most_assists",     PlayerGame.assists,         "Assists"),
            ("most_utility_dmg", PlayerGame.utility_damage,  "Utility Damage"),
        ]
        property_categories = [
            ("best_hs_pct",  "headshot_pct",  "HS%"),
            ("best_kd",      "kd_ratio",      "K/D Ratio"),
        ]

        for key, col, label in column_categories:
            best_pg = (
                PlayerGame.query
                .join(PlayerGame.game)
                .filter(Game.played_at >= year_start)
                .order_by(desc(col))
                .first()
            )
            if not best_pg:
                continue
            val = float(getattr(best_pg, col.key) or 0)
            if val == 0:
                continue
            records[key] = {
                "label": label,
                "value": round(val, 2),
                "username": best_pg.player.username,
                "avatar_url": best_pg.player.avatar_url,
                "steam_id": best_pg.player.steam_id,
                "map_name": best_pg.game.map_name,
                "played_at": best_pg.game.played_at.isoformat() if best_pg.game.played_at else None,
                "match_id": best_pg.game.match_id,
            }

        # Property-based categories require loading all records
        all_pgs = PlayerGame.query.join(PlayerGame.game).filter(Game.played_at >= year_start).all()
        if all_pgs:
            for key, attr, label in property_categories:
                best_pg = max(all_pgs, key=lambda pg, a=attr: getattr(pg, a) or 0)
                val = getattr(best_pg, attr) or 0
                if val == 0:
                    continue
                records[key] = {
                    "label": label,
                    "value": round(float(val), 2),
                    "username": best_pg.player.username,
                    "avatar_url": best_pg.player.avatar_url,
                    "steam_id": best_pg.player.steam_id,
                    "map_name": best_pg.game.map_name,
                    "played_at": best_pg.game.played_at.isoformat() if best_pg.game.played_at else None,
                    "match_id": best_pg.game.match_id,
                }

        return jsonify(records)

    @app.route("/api/stats/problem-players", methods=["GET"])
    def problem_players():
        """Return players ranked by a 'problem score' (low rating, low KD, etc.)."""
        from models import Player
        players = Player.query.all()
        stats = []
        for p in players:
            agg = _aggregate_player_stats(p)
            if agg["games"] == 0:
                continue
            # Problem score: lower is better. Penalise low rating and low K/D
            problem_score = round(
                (1 / max(agg["avg_rating"], 0.01)) + (1 / max(agg["avg_kd"], 0.01)),
                3,
            )
            agg["problem_score"] = problem_score
            stats.append(agg)

        stats.sort(key=lambda x: x["problem_score"], reverse=True)
        return jsonify(stats)

    # ------------------------------------------------------------------ #
    # Steam API                                                             #
    # ------------------------------------------------------------------ #

    @app.route("/api/steam/friends/<steam_id>", methods=["GET"])
    def steam_friends(steam_id):
        """Return Steam friend profiles for the given Steam64 ID."""
        from models import Player
        friend_ids = steam_client.get_friend_list(steam_id, api_key=app.config["STEAM_API_KEY"])
        if friend_ids is None:
            return jsonify({
                "error": (
                    "Could not fetch friends list. "
                    "Ensure your Steam profile is public and your STEAM_API_KEY is set."
                )
            }), 400

        summaries = steam_client.get_player_summaries(friend_ids, api_key=app.config["STEAM_API_KEY"])

        # Mark friends that are already tracked
        tracked_ids = {p.steam_id for p in Player.query.all()}
        for s in summaries:
            s["tracked"] = s["steam_id"] in tracked_ids

        # Sort: tracked first, then alphabetically
        summaries.sort(key=lambda x: (not x["tracked"], x["username"].lower()))
        return jsonify(summaries)

    # ------------------------------------------------------------------ #
    # AI Analysis                                                           #
    # ------------------------------------------------------------------ #

    @app.route("/api/analysis", methods=["GET"])
    def list_analyses():
        from models import AIAnalysis
        analyses = AIAnalysis.query.order_by(AIAnalysis.created_at.desc()).limit(20).all()
        return jsonify([a.to_dict() for a in analyses])

    @app.route("/api/analysis", methods=["POST"])
    def generate_analysis():
        from models import Player, Session, AIAnalysis
        data = request.get_json(force=True) or {}
        scope = data.get("scope", "all_time")   # "all_time" | "session"
        scope_id = data.get("scope_id")         # session id if scope=="session"
        player_ids = data.get("player_ids") or []  # optional list of steam_ids

        if scope == "session" and scope_id:
            session = Session.query.get(scope_id)
            if not session:
                return jsonify({"error": "Session not found"}), 404
            player_stats_list = _aggregate_session_stats(session)
            scope_label = f"session '{session.name}'"
        else:
            if player_ids:
                players = Player.query.filter(Player.steam_id.in_(player_ids[:5])).all()
            else:
                players = Player.query.all()
            player_stats_list = [_aggregate_player_stats(p) for p in players]
            scope_label = "all time"

        if not player_stats_list:
            return jsonify({"error": "No stats available. Sync data first."}), 400

        # Attach per-game breakdown for richer analysis (only available for non-session scope)
        from models import PlayerGame, Game as GameModel
        per_game_data = {}
        if scope != "session" or not scope_id:
            for p in players:
                pgs = (
                    PlayerGame.query
                    .join(PlayerGame.game)
                    .filter(PlayerGame.player_id == p.id)
                    .order_by(GameModel.played_at.desc())
                    .limit(15)
                    .all()
                )
                per_game_data[p.steam_id] = [pg.to_dict() for pg in pgs]

        analysis_text = openai_client.generate_analysis(
            player_stats_list,
            scope=scope_label,
            openai_api_key=app.config["OPENAI_API_KEY"],
            per_game_data=per_game_data,
        )

        record = AIAnalysis(
            scope=scope,
            scope_id=str(scope_id) if scope_id else "all",
            prompt_summary=f"Analysed {len(player_stats_list)} players ({scope_label})",
            analysis=analysis_text,
            model_used="gpt-4o-mini",
        )
        db.session.add(record)
        db.session.commit()

        return jsonify(record.to_dict()), 201

    # ------------------------------------------------------------------ #
    # Helper functions                                                      #
    # ------------------------------------------------------------------ #

    def _aggregate_player_stats(player) -> dict:
        """Return a dict of aggregate stats for a player across their last 15 games.

        Games with zero ADR or zero rating are excluded from the respective
        averages to avoid old/incomplete game records skewing the numbers.
        """
        from models import PlayerGame, Game
        pgs = (
            PlayerGame.query
            .join(PlayerGame.game)
            .filter(PlayerGame.player_id == player.id)
            .order_by(Game.played_at.desc())
            .limit(15)
            .all()
        )
        if not pgs:
            return {
                "steam_id": player.steam_id,
                "username": player.username,
                "avatar_url": player.avatar_url,
                "games": 0,
                "avg_rating": 0.0,
                "avg_kd": 0.0,
                "avg_adr": 0.0,
                "avg_hs_pct": 0.0,
                "avg_leetify_rating": 0.0,
                "win_rate": 0.0,
                "total_kills": 0,
                "total_deaths": 0,
                "total_assists": 0,
            }

        n = len(pgs)
        total_kills = sum(pg.kills for pg in pgs)
        total_deaths = sum(pg.deaths for pg in pgs)
        total_assists = sum(pg.assists for pg in pgs)

        # Only average over games that have valid (non-zero) data
        rated = [pg for pg in pgs if pg.leetify_rating != 0]
        adr_games = [pg for pg in pgs if pg.adr > 0]

        return {
            "steam_id": player.steam_id,
            "username": player.username,
            "avatar_url": player.avatar_url,
            "games": n,
            "avg_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
            "avg_leetify_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
            "avg_kd": round(total_kills / max(total_deaths, 1), 2),
            "avg_adr": round(sum(pg.adr for pg in adr_games) / len(adr_games), 1) if adr_games else 0.0,
            "avg_hs_pct": round(
                sum(pg.headshot_pct for pg in pgs) / n, 1
            ),
            "win_rate": 0.0,  # win/loss requires knowing which team the player was on
            "total_kills": total_kills,
            "total_deaths": total_deaths,
            "total_assists": total_assists,
        }

    def _aggregate_session_stats(session) -> list[dict]:
        """Return aggregate stats for all players in a session."""
        from models import PlayerGame
        result = []
        for player in session.players:
            # Filter player games to only those in this session
            pgs = (
                PlayerGame.query
                .join(PlayerGame.game)
                .filter(
                    PlayerGame.player_id == player.id,
                    # If game.session_id is set use it, otherwise fall back to all
                )
                .all()
            )
            # Prefer games explicitly linked to this session
            session_pgs = [pg for pg in pgs if pg.game.session_id == session.id]
            if session_pgs:
                pgs = session_pgs

            if not pgs:
                continue

            n = len(pgs)
            total_kills = sum(pg.kills for pg in pgs)
            total_deaths = sum(pg.deaths for pg in pgs)
            rated = [pg for pg in pgs if pg.leetify_rating != 0]
            adr_games = [pg for pg in pgs if pg.adr > 0]

            result.append({
                "steam_id": player.steam_id,
                "username": player.username,
                "avatar_url": player.avatar_url,
                "games": n,
                "avg_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
                "avg_leetify_rating": round(sum(pg.leetify_rating for pg in rated) / len(rated), 3) if rated else 0.0,
                "avg_kd": round(total_kills / max(total_deaths, 1), 2),
                "avg_adr": round(sum(pg.adr for pg in adr_games) / len(adr_games), 1) if adr_games else 0.0,
                "avg_hs_pct": round(sum(pg.headshot_pct for pg in pgs) / n, 1),
                "win_rate": 0.0,
                "total_kills": total_kills,
                "total_deaths": total_deaths,
                "total_assists": sum(pg.assists for pg in pgs),
            })

        result.sort(key=lambda x: x["avg_rating"], reverse=True)
        return result

    return app


if __name__ == "__main__":
    import os
    app = create_app()
    debug = os.getenv("FLASK_ENV") == "development"
    app.run(debug=debug, port=5000)
