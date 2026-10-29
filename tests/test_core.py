import io
import time

import chess
import chess.engine
import chess.pgn

from mistake_puzzles import analyze, db, trainer


def test_win_percent_monotonic_and_symmetric():
    assert abs(analyze.win_percent(0) - 50) < 1e-9
    assert analyze.win_percent(300) > analyze.win_percent(100) > 50
    assert abs(analyze.win_percent(200) + analyze.win_percent(-200) - 100) < 1e-6


def test_game_phase():
    assert analyze.game_phase(chess.Board()) == "opening"
    assert analyze.game_phase(chess.Board("8/5k2/8/8/8/3K4/4R3/8 w - - 0 40")) == "endgame"
    mid = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P4/2N1PN2/PPQ1BPPP/R1B2RK1 w - - 0 12")
    assert analyze.game_phase(mid) == "middlegame"


def test_parse_move_san_and_uci():
    b = chess.Board()
    assert trainer.parse_move(b, "Nf3") == chess.Move.from_uci("g1f3")
    assert trainer.parse_move(b, "e2e4") == chess.Move.from_uci("e2e4")
    assert trainer.parse_move(b, "e2e5") is None
    assert trainer.parse_move(b, "") is None


def test_next_state_boxes():
    now = 1000.0
    box, due = trainer.next_state(0, "first", now)
    assert box == 1 and due == now + 86400
    box, _ = trainer.next_state(3, "fail", now)
    assert box == 0
    box, _ = trainer.next_state(6, "first", now)
    assert box == 6


def test_render_board_orientation():
    b = chess.Board()
    white = trainer.render_board(b, chess.WHITE).splitlines()
    black = trainer.render_board(b, chess.BLACK).splitlines()
    assert white[0].startswith("8") and white[-1].strip().startswith("a")
    assert black[0].startswith("1") and black[-1].strip().startswith("h")


class FakeEngine:
    """Подставной движок: в позиции после 3.Bc4 лучший ход g6, ход Nf6 проигрывает."""

    def analyse(self, board, limit, multipv=1):
        n = len(board.move_stack)
        turn = board.turn
        if n == 5:
            return [
                {"pv": [chess.Move.from_uci("g7g6")],
                 "score": chess.engine.PovScore(chess.engine.Cp(0), turn)},
                {"pv": [chess.Move.from_uci("g8h6")],
                 "score": chess.engine.PovScore(chess.engine.Cp(-200), turn)},
            ]
        if n == 6:
            return [{"pv": [chess.Move.from_uci("h5f7")],
                     "score": chess.engine.PovScore(chess.engine.Mate(1), turn)}]
        move = next(iter(board.legal_moves))
        return [{"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(0), turn)}]


def test_analyze_game_finds_blunder():
    game = chess.pgn.read_game(io.StringIO("1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#"))
    puzzles = analyze.analyze_game(FakeEngine(), game, chess.BLACK, min_ply=0)
    assert len(puzzles) == 1
    p = puzzles[0]
    assert p["best"] == "g7g6" and p["played"] == "g8f6"
    assert p["category"] == "blunder"
    assert p["ply"] == 5


def test_db_roundtrip_and_due_order():
    con = db.connect(":memory:")
    con.execute("INSERT INTO games (id, username, color, pgn) VALUES ('g1','Me','white','x')")
    base = {"fen": chess.STARTING_FEN, "color": "white", "played": "a2a3", "best": "e2e4",
            "pv": "e2e4", "best_cp": 30, "played_cp": -50, "category": "mistake",
            "phase": "opening", "tag": ""}
    db.add_puzzles(con, "g1", [dict(base, ply=2, loss=22.0), dict(base, ply=4, loss=45.0)])
    rows = db.due_puzzles(con, "me", limit=10)
    assert [r["ply"] for r in rows] == [4, 2]  # сначала самая большая потеря
    db.update_result(con, rows[0]["id"], 1, time.time() + 86400, True)
    assert len(db.due_puzzles(con, "me", limit=10)) == 1
