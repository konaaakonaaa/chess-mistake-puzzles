"""Отчёт о слабостях по найденным ошибкам."""
from collections import defaultdict

from rich.console import Console
from rich.table import Table

PHASE_RU = {"opening": "дебют", "middlegame": "миттельшпиль", "endgame": "эндшпиль"}
BASE = ("FROM puzzles p JOIN games g ON g.id = p.game_id "
        "WHERE lower(g.username) = lower(?)")


def bar(value, maximum, width=20):
    if not maximum:
        return ""
    return "█" * max(1, round(width * value / maximum))


def report(con, username, console=None):
    console = console or Console()
    g = con.execute("SELECT COUNT(*) AS c, COALESCE(SUM(analyzed), 0) AS a "
                    "FROM games WHERE lower(username) = lower(?)", (username,)).fetchone()
    if not g["c"]:
        console.print("[yellow]Партий нет. Сначала выполните fetch.[/]")
        return
    rows = con.execute("SELECT p.* " + BASE, (username,)).fetchall()
    console.rule(f"[bold]Отчёт: {username}")
    console.print(f"Партий загружено: {g['c']}, проанализировано: {g['a']}, "
                  f"задач найдено: {len(rows)}")
    if not rows:
        return

    blunders = sum(1 for r in rows if r["category"] == "blunder")
    console.print(f"Зевков: {blunders}, ошибок: {len(rows) - blunders}, "
                  f"средняя потеря шансов: {sum(r['loss'] for r in rows) / len(rows):.0f}%")
    missed = sum(1 for r in rows if r["tag"] == "missed_mate")
    allowed = sum(1 for r in rows if r["tag"] == "allowed_mate")
    if missed or allowed:
        console.print(f"Пропущено матов: {missed}, допущено матов: {allowed}")

    by_phase = defaultdict(list)
    for r in rows:
        by_phase[r["phase"]].append(r["loss"])
    mx = max(len(v) for v in by_phase.values())
    t = Table(title="Ошибки по фазам партии")
    t.add_column("Фаза"); t.add_column("Задач"); t.add_column("Ср. потеря"); t.add_column("")
    for ph in ("opening", "middlegame", "endgame"):
        v = by_phase.get(ph, [])
        if v:
            t.add_row(PHASE_RU[ph], str(len(v)), f"{sum(v) / len(v):.0f}%", bar(len(v), mx))
    console.print(t)

    by_color = defaultdict(int)
    for r in rows:
        by_color[r["color"]] += 1
    console.print(f"Белыми: {by_color['white']} ошибок, чёрными: {by_color['black']}")

    games_by_op = defaultdict(int)
    for r in con.execute("SELECT opening FROM games WHERE analyzed = 1 "
                         "AND lower(username) = lower(?)", (username,)):
        games_by_op[(r["opening"] or "Без дебюта").split(":")[0]] += 1
    errs_by_op = defaultdict(int)
    for r in con.execute("SELECT g.opening AS o " + BASE, (username,)):
        errs_by_op[(r["o"] or "Без дебюта").split(":")[0]] += 1
    t = Table(title="Дебюты с наибольшим числом ошибок")
    t.add_column("Дебют"); t.add_column("Партий"); t.add_column("Задач"); t.add_column("На партию")
    for op, cnt in sorted(errs_by_op.items(), key=lambda x: -x[1])[:5]:
        n = games_by_op.get(op, 0)
        t.add_row(op, str(n), str(cnt), f"{cnt / n:.1f}" if n else "-")
    console.print(t)

    worst = max(by_phase, key=lambda k: len(by_phase[k]))
    console.print(f"\n[bold]Главная слабость:[/] {PHASE_RU[worst]} "
                  f"({len(by_phase[worst])} из {len(rows)} ошибок)")

    solved = sum(1 for r in rows if r["solved"] > 0)
    mastered = sum(1 for r in rows if r["box"] >= 3)
    console.print(f"Прогресс тренировки: решено хотя бы раз {solved}/{len(rows)}, "
                  f"усвоено (коробка 3+) {mastered}/{len(rows)}")
