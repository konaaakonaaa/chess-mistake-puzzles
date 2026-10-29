"""Анализ партий Stockfish'ем и поиск позиций-задач."""
import io
import math
import os
import shutil

import chess
import chess.engine
import chess.pgn

MATE = 10000


def win_percent(cp):
    """Вероятность выигрыша в % по оценке в сантипешках (формула Lichess)."""
    cp = max(-1000, min(1000, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def game_phase(board):
    """opening / middlegame / endgame по ходу и количеству фигур."""
    pieces = sum(len(board.pieces(t, c))
                 for t in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
                 for c in (chess.WHITE, chess.BLACK))
    if board.fullmove_number <= 10 and pieces >= 12:
        return "opening"
    if pieces <= 6:
        return "endgame"
    return "middlegame"


def find_engine(path=None):
    cand = path or os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not cand:
        raise SystemExit(
            "Stockfish не найден. Скачайте его с https://stockfishchess.org/download/ "
            "и укажите путь: --engine путь/к/stockfish или переменная STOCKFISH_PATH")
    return cand


def evaluate(engine, board, depth):
    """Оценки позиции с точки зрения стороны, которая ходит (до 2 лучших линий)."""
    if board.is_checkmate():
        return [{"cp": -MATE, "move": None, "pv": []}]
    if board.is_game_over():
        return [{"cp": 0, "move": None, "pv": []}]
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
    if isinstance(infos, dict):
        infos = [infos]
    result = []
    for info in infos:
        pv = info.get("pv") or []
        result.append({
            "cp": info["score"].pov(board.turn).score(mate_score=MATE),
            "move": pv[0] if pv else None,
            "pv": pv[:5],
        })
    return result


def analyze_game(engine, game, color, depth=14, min_loss=20.0, min_ply=6,
                 min_gap=10.0, min_best=25.0):
    """Находит ходы игрока `color`, которые стоит превратить в задачи.

    Условия попадания хода в задачи:
      * потеря шансов на победу >= min_loss (в процентных пунктах);
      * позиция до хода не была уже проигранной (шансы >= min_best);
      * лучший ход заметно сильнее второго (gap >= min_gap), то есть решение одно.
    """
    board = game.board()
    boards = [board.copy()]
    moves = []
    for move in game.mainline_moves():
        moves.append(move)
        board.push(move)
        boards.append(board.copy())

    cache = {}

    def ev(i):
        if i not in cache:
            cache[i] = evaluate(engine, boards[i], depth)
        return cache[i]

    puzzles = []
    for i, move in enumerate(moves):
        if i < min_ply or boards[i].turn != color:
            continue
        lines = ev(i)
        best = lines[0]
        if best["move"] is None or move == best["move"]:
            continue

        best_cp = best["cp"]
        played_cp = -ev(i + 1)[0]["cp"]
        w_best, w_played = win_percent(best_cp), win_percent(played_cp)
        loss = w_best - w_played

        if loss < min_loss or w_best < min_best:
            continue
        if len(lines) > 1 and w_best - win_percent(lines[1]["cp"]) < min_gap:
            continue

        if best_cp >= MATE - 100:
            tag = "missed_mate"
        elif played_cp <= -(MATE - 100):
            tag = "allowed_mate"
        else:
            tag = ""

        puzzles.append({
            "ply": i,
            "fen": boards[i].fen(),
            "color": "white" if color == chess.WHITE else "black",
            "played": move.uci(),
            "best": best["move"].uci(),
            "pv": " ".join(m.uci() for m in best["pv"]),
            "best_cp": best_cp,
            "played_cp": played_cp,
            "loss": round(loss, 1),
            "category": "blunder" if loss >= 30 else "mistake",
            "phase": game_phase(boards[i]),
            "tag": tag,
        })
    return puzzles


def run_analysis(con, username, engine_path, depth=14, max_games=20,
                 min_loss=20.0, threads=2, hash_mb=128, console=None):
    from . import db

    rows = con.execute(
        "SELECT id, color, pgn FROM games "
        "WHERE analyzed = 0 AND lower(username) = lower(?) LIMIT ?",
        (username, max_games)).fetchall()
    if not rows:
        return 0, 0

    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    total_games, total_puzzles = 0, 0
    try:
        engine.configure({"Threads": threads, "Hash": hash_mb})
        for k, row in enumerate(rows, 1):
            game = chess.pgn.read_game(io.StringIO(row["pgn"]))
            color = chess.WHITE if row["color"] == "white" else chess.BLACK
            puzzles = analyze_game(engine, game, color, depth, min_loss)
            added = db.add_puzzles(con, row["id"], puzzles)
            con.execute("UPDATE games SET analyzed = 1 WHERE id = ?", (row["id"],))
            con.commit()
            total_games += 1
            total_puzzles += added
            if console:
                console.print(f"[{k}/{len(rows)}] {row['id']}: задач найдено {added}")
    finally:
        engine.quit()
    return total_games, total_puzzles
