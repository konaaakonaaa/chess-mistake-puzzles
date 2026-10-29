"""SQLite-хранилище: партии, задачи и состояние повторения."""
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id        TEXT PRIMARY KEY,
    username  TEXT NOT NULL,
    color     TEXT NOT NULL,
    white     TEXT,
    black     TEXT,
    result    TEXT,
    opening   TEXT,
    played    TEXT,
    pgn       TEXT NOT NULL,
    analyzed  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS puzzles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    TEXT NOT NULL REFERENCES games(id),
    ply        INTEGER NOT NULL,
    fen        TEXT NOT NULL,
    color      TEXT NOT NULL,
    played     TEXT NOT NULL,
    best       TEXT NOT NULL,
    pv         TEXT,
    best_cp    INTEGER,
    played_cp  INTEGER,
    loss       REAL,
    category   TEXT,
    phase      TEXT,
    tag        TEXT,
    box        INTEGER NOT NULL DEFAULT 0,
    due        REAL NOT NULL DEFAULT 0,
    attempts   INTEGER NOT NULL DEFAULT 0,
    solved     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (game_id, ply)
);
"""


def connect(path="data/puzzles.db"):
    path = str(path)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def add_puzzles(con, game_id, puzzles):
    """Сохраняет задачи партии, возвращает сколько новых добавлено."""
    added = 0
    for p in puzzles:
        cur = con.execute(
            """INSERT OR IGNORE INTO puzzles
               (game_id, ply, fen, color, played, best, pv, best_cp, played_cp,
                loss, category, phase, tag)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (game_id, p["ply"], p["fen"], p["color"], p["played"], p["best"],
             p["pv"], p["best_cp"], p["played_cp"], p["loss"], p["category"],
             p["phase"], p["tag"]),
        )
        added += cur.rowcount
    con.commit()
    return added


def due_puzzles(con, username, limit=10, category=None, phase=None, now=None):
    """Задачи, которые пора повторить (новые идут первыми по величине ошибки)."""
    now = time.time() if now is None else now
    sql = ("SELECT p.* FROM puzzles p JOIN games g ON g.id = p.game_id "
           "WHERE lower(g.username) = lower(?) AND p.due <= ?")
    args = [username, now]
    if category:
        sql += " AND p.category = ?"
        args.append(category)
    if phase:
        sql += " AND p.phase = ?"
        args.append(phase)
    sql += " ORDER BY p.due ASC, p.loss DESC LIMIT ?"
    args.append(limit)
    return con.execute(sql, args).fetchall()


def update_result(con, puzzle_id, box, due, solved_first_try):
    con.execute(
        "UPDATE puzzles SET box=?, due=?, attempts=attempts+1, "
        "solved=solved+? WHERE id=?",
        (box, due, 1 if solved_first_try else 0, puzzle_id),
    )
    con.commit()
