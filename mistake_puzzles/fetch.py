"""Загрузка партий игрока из API Lichess (PGN-поток)."""
import io
import time

import chess.pgn
import requests

API = "https://lichess.org/api/games/user/{}"


def download_pgn(username, n=100, perf=None, token=None, console=None):
    """Возвращает текст PGN с последними n партиями игрока."""
    params = {"max": n, "opening": "true", "moves": "true", "tags": "true",
              "clocks": "false", "evals": "false"}
    if perf:
        params["perfType"] = perf
    headers = {"Accept": "application/x-chess-pgn"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for _ in range(3):
        r = requests.get(API.format(username), params=params,
                         headers=headers, timeout=60)
        if r.status_code == 429:
            if console:
                console.print("[yellow]Лимит API, жду 60 секунд...[/]")
            time.sleep(60)
            continue
        if r.status_code == 404:
            raise SystemExit(f"Игрок '{username}' не найден на Lichess")
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text
    raise SystemExit("Lichess несколько раз ответил 429. Попробуйте позже.")


def iter_games(pgn_text):
    stream = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            return
        yield game


def game_record(game, username):
    """Превращает партию в запись для БД. None, если партия не подходит."""
    h = game.headers
    if h.get("Variant", "Standard") != "Standard":
        return None
    low = username.lower()
    if h.get("White", "").lower() == low:
        color = "white"
    elif h.get("Black", "").lower() == low:
        color = "black"
    else:
        return None
    gid = h.get("Site", "").rstrip("/").rsplit("/", 1)[-1][:8]
    if not gid:
        return None
    return {
        "id": gid,
        "username": username,
        "color": color,
        "white": h.get("White"),
        "black": h.get("Black"),
        "result": h.get("Result"),
        "opening": h.get("Opening", "Без дебюта"),
        "played": f"{h.get('UTCDate', '')} {h.get('UTCTime', '')}".strip(),
        "pgn": str(game),
    }


def save_games(con, records):
    new = 0
    for r in records:
        cur = con.execute(
            """INSERT OR IGNORE INTO games
               (id, username, color, white, black, result, opening, played, pgn)
               VALUES (:id,:username,:color,:white,:black,:result,:opening,:played,:pgn)""",
            r,
        )
        new += cur.rowcount
    con.commit()
    return new


def fetch_user(con, username, n=100, perf=None, token=None, console=None):
    text = download_pgn(username, n, perf, token, console)
    records = []
    for game in iter_games(text):
        rec = game_record(game, username)
        if rec:
            records.append(rec)
    return len(records), save_games(con, records)
