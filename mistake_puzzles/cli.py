"""Командная строка: fetch, analyze, train, stats, export."""
import argparse
import os

from rich.console import Console

from . import db

console = Console()


def build_parser():
    p = argparse.ArgumentParser(
        prog="mistake-puzzles",
        description="Задачи из собственных ошибок в партиях Lichess")
    p.add_argument("--db", default="data/puzzles.db", help="путь к базе SQLite")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="загрузить партии игрока")
    f.add_argument("username")
    f.add_argument("-n", type=int, default=100, help="сколько партий (по умолчанию 100)")
    f.add_argument("--perf", help="bullet/blitz/rapid/classical")
    f.add_argument("--token", default=os.environ.get("LICHESS_TOKEN"),
                   help="токен Lichess (или переменная LICHESS_TOKEN)")

    a = sub.add_parser("analyze", help="проанализировать партии Stockfish'ем")
    a.add_argument("username")
    a.add_argument("--engine", help="путь к Stockfish (или STOCKFISH_PATH)")
    a.add_argument("--depth", type=int, default=14)
    a.add_argument("--max-games", type=int, default=20)
    a.add_argument("--min-loss", type=float, default=20.0,
                   help="минимальная потеря шансов на победу в %% (по умолчанию 20)")
    a.add_argument("--threads", type=int, default=2)
    a.add_argument("--hash", type=int, default=128, help="память движка, МБ")

    t = sub.add_parser("train", help="решать задачи")
    t.add_argument("username")
    t.add_argument("--limit", type=int, default=10)
    t.add_argument("--category", choices=["blunder", "mistake"])
    t.add_argument("--phase", choices=["opening", "middlegame", "endgame"])

    s = sub.add_parser("stats", help="отчёт о слабостях")
    s.add_argument("username")

    e = sub.add_parser("export", help="выгрузить задачи в PGN")
    e.add_argument("username")
    e.add_argument("-o", "--output", default="puzzles.pgn")
    e.add_argument("--category", choices=["blunder", "mistake"])
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    con = db.connect(args.db)

    if args.cmd == "fetch":
        from .fetch import fetch_user
        with console.status(f"Загружаю партии {args.username}..."):
            total, new = fetch_user(con, args.username, args.n, args.perf,
                                    args.token, console)
        console.print(f"Получено партий: {total}, новых сохранено: {new}")
    elif args.cmd == "analyze":
        from .analyze import find_engine, run_analysis
        games, puzzles = run_analysis(
            con, args.username, find_engine(args.engine), args.depth,
            args.max_games, args.min_loss, args.threads, args.hash, console)
        if games == 0:
            console.print("[yellow]Нет непроанализированных партий. Выполните fetch.[/]")
        else:
            console.print(f"[green]Готово:[/] партий {games}, новых задач {puzzles}")
    elif args.cmd == "train":
        from .trainer import train
        train(con, args.username, args.limit, args.category, args.phase, console)
    elif args.cmd == "stats":
        from .stats import report
        report(con, args.username, console)
    elif args.cmd == "export":
        from .export import export_pgn
        n = export_pgn(con, args.username, args.output, args.category)
        console.print(f"Выгружено задач: {n} → {args.output}")
