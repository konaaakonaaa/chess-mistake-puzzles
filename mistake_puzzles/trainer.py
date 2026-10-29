"""Терминальный тренажёр с интервальным повторением (коробки Лейтнера)."""
import time
from collections import deque

import chess
from rich.console import Console
from rich.panel import Panel

from . import db

INTERVALS_DAYS = [0, 1, 3, 7, 14, 30, 60]
MAX_TRIES = 3
PIECE_RU = {chess.PAWN: "пешка", chess.KNIGHT: "конь", chess.BISHOP: "слон",
            chess.ROOK: "ладья", chess.QUEEN: "ферзь", chess.KING: "король"}


def next_state(box, outcome, now=None):
    """outcome: 'first' (с первой попытки), 'later' (со второй или с подсказкой), 'fail'."""
    now = time.time() if now is None else now
    if outcome == "first":
        box = min(box + 1, len(INTERVALS_DAYS) - 1)
    elif outcome == "later":
        box = max(box, 1)
    else:
        box = 0
    return box, now + INTERVALS_DAYS[box] * 86400


def render_board(board, color):
    files = range(8) if color == chess.WHITE else range(7, -1, -1)
    ranks = range(7, -1, -1) if color == chess.WHITE else range(8)
    lines = []
    for r in ranks:
        row = []
        for f in files:
            piece = board.piece_at(chess.square(f, r))
            row.append(piece.unicode_symbol(invert_color=True) if piece else "·")
        lines.append(f"{r + 1}  " + " ".join(row))
    lines.append("   " + " ".join("abcdefgh"[f] for f in files))
    return "\n".join(lines)


def parse_move(board, text):
    text = text.strip()
    if not text:
        return None
    try:
        return board.parse_san(text)
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(text.lower())
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def format_line(board, ucis):
    b = board.copy()
    parts = []
    for k, u in enumerate(ucis):
        try:
            m = chess.Move.from_uci(u)
        except ValueError:
            break
        if m not in b.legal_moves:
            break
        if b.turn == chess.WHITE:
            parts.append(f"{b.fullmove_number}.")
        elif k == 0:
            parts.append(f"{b.fullmove_number}...")
        parts.append(b.san(m))
        b.push(m)
    return " ".join(parts)


def fmt_eval(cp):
    if cp is None:
        return "?"
    return "мат" if abs(cp) >= 9900 else f"{cp / 100:+.1f}"


def reveal(console, board, row):
    best = chess.Move.from_uci(row["best"])
    played = chess.Move.from_uci(row["played"])
    console.print(f"\n[green]Лучший ход:[/] {board.san(best)} (оценка {fmt_eval(row['best_cp'])})")
    line = format_line(board, row["pv"].split())
    if line:
        console.print(f"[green]Основная линия:[/] {line}")
    console.print(f"[red]В партии вы сыграли:[/] {board.san(played)} "
                  f"(оценка {fmt_eval(row['played_cp'])}, потеря шансов {row['loss']:.0f}%)")
    console.print(f"[dim]Партия: https://lichess.org/{row['game_id']}#{row['ply']}[/]\n")


def ask(console, row):
    """Один раунд. Возвращает 'first' | 'later' | 'fail' | 'quit'."""
    board = chess.Board(row["fen"])
    color = board.turn
    best = chess.Move.from_uci(row["best"])
    side = "белых" if color == chess.WHITE else "чёрных"
    title = f"Задача #{row['id']} · {row['category']} · {row['phase']}"
    console.print(Panel(render_board(board, color), title=title,
                        subtitle=f"Ход {side}", expand=False))
    console.print("[dim]Введите ход (Nf3 или e2e4). Команды: hint, show, quit[/]")

    tries, hints = 0, 0
    while True:
        try:
            text = console.input("[bold cyan]Ваш ход > [/]").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"
        low = text.lower()
        if low in ("q", "quit", "exit", "выход"):
            return "quit"
        if low in ("show", "ответ", "s"):
            reveal(console, board, row)
            return "fail"
        if low in ("hint", "подсказка", "h"):
            hints += 1
            piece = board.piece_at(best.from_square)
            if hints == 1:
                console.print(f"Подсказка: ходить нужно фигурой «{PIECE_RU[piece.piece_type]}»")
            else:
                console.print(f"Подсказка: ход с поля {chess.square_name(best.from_square)}")
            continue

        move = parse_move(board, text)
        if move is None:
            console.print("[yellow]Не понял ход или он невозможен. Пример: Nf3 или g1f3[/]")
            continue
        if move == best:
            console.print("[bold green]Верно![/]")
            reveal(console, board, row)
            return "first" if tries == 0 and hints == 0 else "later"
        tries += 1
        if tries >= MAX_TRIES:
            console.print("[red]Попытки закончились.[/]")
            reveal(console, board, row)
            return "fail"
        console.print(f"[red]Нет, это не лучший ход.[/] Попыток осталось: {MAX_TRIES - tries}")


def train(con, username, limit=10, category=None, phase=None, console=None):
    console = console or Console()
    rows = db.due_puzzles(con, username, limit, category, phase)
    if not rows:
        console.print("[yellow]Нет задач к повторению. Сначала выполните fetch и analyze "
                      "или вернитесь позже.[/]")
        return
    queue = deque((dict(r), False) for r in rows)
    score = {"first": 0, "later": 0, "fail": 0}
    while queue:
        row, is_retry = queue.popleft()
        outcome = ask(console, row)
        if outcome == "quit":
            break
        score[outcome] += 1
        if not is_retry:
            box, due = next_state(row["box"], outcome)
            db.update_result(con, row["id"], box, due, outcome == "first")
            if outcome == "fail":
                queue.append((row, True))
    total = sum(score.values())
    console.print(f"\n[bold]Итог сессии:[/] решено с первого раза {score['first']}, "
                  f"с подсказкой или со второй попытки {score['later']}, "
                  f"не решено {score['fail']} (из {total} раундов)")
