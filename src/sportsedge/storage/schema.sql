-- sports-edge-lab historical database schema

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    sport TEXT NOT NULL,              -- 'nfl' | 'soccer'
    league TEXT NOT NULL,             -- 'NFL' | 'E0' (EPL) | ...
    season TEXT NOT NULL,
    week TEXT,
    game_date TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    result TEXT,                      -- 'H' | 'A' | 'D'
    home_odds_decimal REAL,           -- closing market odds, decimal format
    away_odds_decimal REAL,
    draw_odds_decimal REAL,           -- soccer only
    spread_line REAL,
    total_line REAL,
    source TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS elo_ratings (
    sport TEXT NOT NULL,
    league TEXT NOT NULL,
    team TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    rating REAL NOT NULL,
    PRIMARY KEY (sport, league, team, as_of_date)
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport TEXT NOT NULL,
    league TEXT NOT NULL,
    event_ticker TEXT,                -- Kalshi event ticker when source='kalshi'
    game_id TEXT,                     -- fk to games.game_id once matched
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    commence_time TEXT,
    selection TEXT NOT NULL,          -- 'home' | 'away' | 'draw'
    yes_bid REAL,
    yes_ask REAL,
    implied_prob_mid REAL,
    source TEXT NOT NULL,             -- 'kalshi' | 'theoddsapi'
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    game_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    p_home REAL NOT NULL,
    p_draw REAL,
    p_away REAL NOT NULL,
    PRIMARY KEY (game_id, model_version)
);

CREATE TABLE IF NOT EXISTS bets (
    bet_id TEXT PRIMARY KEY,
    placed_at TEXT NOT NULL,
    game_id TEXT NOT NULL,
    sport TEXT NOT NULL,
    league TEXT NOT NULL,
    market TEXT NOT NULL,             -- 'moneyline'
    selection TEXT NOT NULL,          -- 'home' | 'away' | 'draw'
    model_prob REAL NOT NULL,
    model_version TEXT NOT NULL,
    market_odds_decimal REAL NOT NULL,
    book TEXT NOT NULL,               -- 'kalshi' | book name
    edge_pct REAL NOT NULL,
    stake REAL NOT NULL,
    kelly_fraction REAL,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'won'|'lost'|'push'
    closing_odds_decimal REAL,
    clv_pct REAL,
    result_logged_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    run_at TEXT NOT NULL,
    sport TEXT NOT NULL,
    league TEXT NOT NULL,
    model_version TEXT NOT NULL,
    params_json TEXT,
    n_games INTEGER,
    n_bets INTEGER,
    log_loss REAL,
    brier_score REAL,
    roi_pct REAL,
    notes TEXT
);
