"""Экспорт задач в PGN (можно импортировать в исследование Lichess)."""
import chess
import chess.pgn

from . import db


def export_pgn(con, username, path, category=None):
    sql = ("SELECT p.* FROM puzzles p JOIN games g ON g.id = p.game_id "
           "WHERE lower(g.username) = lower(?)")
    args = [username]
    if category:
        sql += " AND p.category = ?"
        args.append(category)
    sql += " ORDER BY p.loss DESC"
    rows = con.execute(sql, args).fetchall()

    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            board = chess.Board(r["fen"])
            game = chess.pgn.Game()
            game.setup(board)
            game.headers["Event"] = f"Задача #{r['id']} ({r['category']}, {r['phase']})"
            game.headers["Site"] = f"https://lichess.org/{r['game_id']}#{r['ply']}"
            best = game.add_variation(chess.Move.from_uci(r["best"]))
            best.comment = f"Лучший ход, оценка {r['best_cp']} cp"
            played = game.add_variation(chess.Move.from_uci(r["played"]))
            played.comment = f"Сыграно в партии, оценка {r['played_cp']} cp"
            print(game, file=f, end="\n\n")
    return len(rows)
