# CS-Monday-Tracker

A web dashboard used to track the progress and performance of the muck boys CS Monday stats — powered by the [Leetify](https://leetify.com) API with optional AI-powered analysis via OpenAI.

## Features

- **Current Session** – stats for the most recent Monday gaming session
- **All-Time Stats** – cumulative leaderboard across all tracked games (HLTV Rating, K/D, ADR, HS%)
- **Problem Players** – ranked list of who is letting the team down
- **AI Analysis** – ask GPT to identify problem areas and give each player actionable tips
- **Sync** – pull the latest match data from Leetify with one click

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Required | Description |
|---|---|---|
| `LEETIFY_API_KEY` | ✅ Yes | Your Leetify API key (find it at [leetify.com/app/settings](https://leetify.com/app/settings)) |
| `OPENAI_API_KEY` | Optional | OpenAI key for AI analysis |
| `SECRET_KEY` | Recommended | Random string for Flask sessions |

> **Security:** Never commit your `.env` file. It is already in `.gitignore`.

### 3. Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

## Workflow

1. **Players tab** – add each player by their Steam64 ID (find yours at [steamid.io](https://steamid.io))
2. **Current Session tab** – click **+ New Session**, select players, and click **Create**
3. Click **🔄 Sync Leetify** to pull the latest games for all tracked players
4. Browse the **All-Time Stats** and **Problem Players** tabs
5. Visit the **AI Analysis** tab and click **Generate Analysis** for a GPT-powered team report

## Running Tests

```bash
python -m pytest tests.py -v
```

## Project Structure

```
app.py              Flask application & REST API
config.py           Configuration (reads .env)
extensions.py       Flask extension instances
models.py           SQLAlchemy models (Player, Game, Session, AIAnalysis)
leetify.py          Leetify API client
openai_client.py    OpenAI integration
tests.py            Pytest test suite
templates/
  dashboard.html    Single-page dashboard
static/
  css/style.css     Dark-mode GitHub-style CSS
  js/app.js         Vanilla JS dashboard logic
```

