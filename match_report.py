"""
Build a match-report workbook (and CSVs) from match.py log folders.

    python match_report.py                                  # every run in match_logs/report
    python match_report.py match_logs/report/<run> ...      # specific runs
    python match_report.py --out my_report.xlsx

Writes, next to the workbook:
    report_games.csv        one row per game
    report_agent_games.csv  one row per agent per game (style statistics)
    report_moves.csv        every move of every game
    report_summary.csv      scoreline per matchup (plain numbers)

The workbook needs openpyxl (`pip install openpyxl`); the CSVs do not.
Summary sheets use formulas over the Games / AgentGames sheets, so editing or
filtering the raw rows recalculates them in Excel.
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

import chess

from agents import aggression_agent
from engine.evaluation import PIECE_VALUES

# Positions that identify a named opening line (deepest one reached wins).
NAMED_LINES = [
    ("King's Gambit", "e4 e5 f4"),
    ("King's Gambit Accepted", "e4 e5 f4 exf4"),
    ("Falkbeer Countergambit", "e4 e5 f4 d5"),
    ("Elephant Gambit", "e4 e5 Nf3 d5"),
    ("Evans Gambit", "e4 e5 Nf3 Nc6 Bc4 Bc5 b4"),
    ("Scotch Gambit", "e4 e5 Nf3 Nc6 d4 exd4 Bc4"),
    ("Two Knights: Ng5 (Fried Liver try)", "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5"),
    ("Smith-Morra Gambit", "e4 c5 d4 cxd4 c3"),
    ("Caro-Kann: Alien Gambit", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Ng5"),
    ("Caro-Kann: Martian Gambit", "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng5 Bg6 N1f3 h6 Ne6"),
    ("Albin Countergambit", "d4 d5 c4 e5"),
    ("Budapest Gambit", "d4 Nf6 c4 e5"),
]

ORANGE = "E8772E"
HEADER_FILL = "2B2A28"
FONT = "Arial"


def _epd_after(line: str) -> str:
    board = chess.Board()
    for san in line.split():
        board.push_san(san)
    return board.epd()


NAMED_EPDS = {_epd_after(line): (len(line.split()), name) for name, line in NAMED_LINES}


def material(board: chess.Board) -> int:
    """White minus Black, centipawns."""
    total = 0
    for pt, v in PIECE_VALUES.items():
        total += v * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
    return total


# ------------------------------------------------------------------ loading --
def load_runs(folders: List[Path]) -> List[dict]:
    runs = []
    for folder in folders:
        data = json.loads((folder / "games.json").read_text())
        g0 = data["games"][0]
        a_name = g0["white"] if g0["a_is_white"] else g0["black"]
        b_name = g0["black"] if g0["a_is_white"] else g0["white"]
        runs.append({"folder": folder, "summary": data["summary"], "games": data["games"],
                     "a": a_name, "b": b_name, "match": f"{a_name} vs {b_name}"})
    return runs


# ---------------------------------------------------------------- analysis --
def analyse_game(run: dict, g: dict):
    """Return (game_row, [agent_row_white, agent_row_black], move_rows)."""
    board = chess.Board()
    names = {chess.WHITE: g["white"], chess.BLACK: g["black"]}
    stats = {c: dict(moves=0, searched=0, book=0, captures=0, checks=0, promotions=0,
                     castled_ply=None, castle_side="", first_capture=None, first_check=None,
                     king_moves=0, material_won=0, material_drops=0, sacrifices=0,
                     nodes=0, time_s=0.0, depth_sum=0, max_time=0.0, eval_sum=0.0)
             for c in (chess.WHITE, chess.BLACK)}
    opening_name, opening_depth = "", 0
    move_rows = []
    moves = g["moves"]
    for i, m in enumerate(moves):
        mover = board.turn
        s = stats[mover]
        move = chess.Move.from_uci(m["uci"])
        sign = 1 if mover == chess.WHITE else -1
        before = material(board) * sign
        is_capture = board.is_capture(move)
        victim = None
        if is_capture:
            victim = (chess.PAWN if board.is_en_passant(move)
                      else board.piece_type_at(move.to_square))
        is_castle = board.is_castling(move)
        castle_side = ("O-O" if board.is_kingside_castling(move) else "O-O-O") if is_castle else ""
        is_king_move = board.piece_type_at(move.from_square) == chess.KING and not is_castle
        in_book = (names[mover] == aggression_agent.NAME
                   and move in aggression_agent.BOOK[mover].get(board.epd(), {}))
        board.push(move)
        gives_check = board.is_check()
        hit = NAMED_EPDS.get(board.epd())
        if hit and hit[0] >= opening_depth:
            opening_depth, opening_name = hit

        ply = m["ply"]
        s["moves"] += 1
        s["book"] += in_book
        if is_capture:
            s["captures"] += 1
            s["material_won"] += PIECE_VALUES[victim]
            s["first_capture"] = s["first_capture"] or ply
        if gives_check:
            s["checks"] += 1
            s["first_check"] = s["first_check"] or ply
        if move.promotion:
            s["promotions"] += 1
        if is_castle:
            s["castled_ply"], s["castle_side"] = ply, castle_side
        s["king_moves"] += is_king_move
        searched = m["source"] == "agent" and (m["depth"] or 0) > 0
        if searched:
            s["searched"] += 1
            s["nodes"] += m["nodes"]
            s["time_s"] += m["time_s"]
            s["depth_sum"] += m["depth"]
            s["max_time"] = max(s["max_time"], m["time_s"])
            s["eval_sum"] += m["score"] * sign

        # Net material over this move and the opponent's reply.
        reply_board = board.copy(stack=False)
        if i + 1 < len(moves) and not board.is_game_over():
            reply_board.push(chess.Move.from_uci(moves[i + 1]["uci"]))
        net = material(reply_board) * sign - before
        dropped = net <= -200
        if dropped:
            s["material_drops"] += 1
            # The mover's own search still saw >= 1.5 pawns of compensation.
            if searched and m["score"] * sign >= material(reply_board) * sign + 150:
                s["sacrifices"] += 1

        move_rows.append({
            "match": run["match"], "game": g["game_no"], "ply": ply,
            "move_no": (ply + 1) // 2, "color": m["color"], "player": m["player"],
            "side": "A" if (m["color"] == "white") == g["a_is_white"] else "B",
            "san": m["san"], "uci": m["uci"], "source": m["source"],
            "book": "yes" if in_book else "", "score": m["score"], "depth": m["depth"],
            "nodes": m["nodes"], "time_s": m["time_s"],
            "capture": "yes" if is_capture else "", "check": "yes" if gives_check else "",
            "material_after": material(board), "material_net_2ply": net,
            "fen_after": m["fen_after"],
        })

    winner_color = {"1-0": chess.WHITE, "0-1": chess.BLACK}.get(g["result"])
    final_eval = next((m["score"] for m in reversed(moves)
                       if m["source"] == "agent" and (m["depth"] or 0) > 0), None)
    a_name, b_name = run["a"], run["b"]
    opening_san = " ".join(m["san"] for m in moves[:len(g["opening"])])
    first_moves = " ".join(m["san"] for m in moves[:12])
    game_row = {
        "match": run["match"], "game": g["game_no"], "white": g["white"], "black": g["black"],
        "agent_a": a_name, "agent_b": b_name,
        "a_colour": "White" if g["a_is_white"] else "Black",
        "result": g["result"],
        "winner": "" if winner_color is None else names[winner_color],
        "loser": "" if winner_color is None else names[not winner_color],
        "winning_colour": "" if winner_color is None else ("White" if winner_color else "Black"),
        "termination": g["termination"], "plies": g["plies"],
        "full_moves": (g["plies"] + 1) // 2, "duration_s": g["duration_s"],
        "named_opening": opening_name, "opening_plies_san": opening_san,
        "first_12_plies": first_moves, "final_material_white": material(board),
        "final_eval_white": final_eval,
    }
    agent_rows = []
    for color in (chess.WHITE, chess.BLACK):
        s = stats[color]
        opp = names[not color]
        res = "D" if winner_color is None else ("W" if winner_color == color else "L")
        sign = 1 if color == chess.WHITE else -1
        agent_rows.append({
            "match": run["match"], "game": g["game_no"], "agent": names[color], "opponent": opp,
            "colour": "White" if color == chess.WHITE else "Black",
            "result": res, "points": {"W": 1.0, "D": 0.5, "L": 0.0}[res],
            "termination": g["termination"], "plies": g["plies"],
            "moves": s["moves"], "searched_moves": s["searched"], "book_moves": s["book"],
            "captures": s["captures"], "checks": s["checks"], "promotions": s["promotions"],
            "castled": "yes" if s["castled_ply"] else "no", "castle_side": s["castle_side"],
            "castle_ply": s["castled_ply"], "first_capture_ply": s["first_capture"],
            "first_check_ply": s["first_check"], "king_moves": s["king_moves"],
            "material_captured_cp": s["material_won"],
            "material_drops": s["material_drops"], "sacrifices": s["sacrifices"],
            "final_material_own": material(board) * sign,
            "total_nodes": s["nodes"], "total_time_s": round(s["time_s"], 4),
            "depth_sum": s["depth_sum"], "max_time_s": round(s["max_time"], 4),
            "eval_sum_own": round(s["eval_sum"], 2),
        })
    return game_row, agent_rows, move_rows


def summary_rows(runs, games, agent_games) -> List[dict]:
    """Plain-number version of the Summary sheet (for the CSV and for checking formulas)."""
    out = []
    for run in runs:
        gs = [g for g in games if g["match"] == run["match"]]
        a, b = run["a"], run["b"]
        def cnt(**kw):
            return sum(all(g[k] == v for k, v in kw.items()) for g in gs)
        ag = [r for r in agent_games if r["match"] == run["match"]]
        def eff(agent):
            rows = [r for r in ag if r["agent"] == agent]
            sm = sum(r["searched_moves"] for r in rows)
            return (sum(r["total_nodes"] for r in rows) / sm if sm else 0,
                    sum(r["total_time_s"] for r in rows) / sm if sm else 0)
        na, ta = eff(a)
        nb, tb = eff(b)
        out.append({
            "match": run["match"], "agent_a": a, "agent_b": b,
            "depth_a": run["summary"]["depth_a"], "depth_b": run["summary"]["depth_b"],
            "games": len(gs), "a_wins": cnt(winner=a), "b_wins": cnt(winner=b),
            "draws": cnt(winner=""),
            "a_points": cnt(winner=a) + 0.5 * cnt(winner=""),
            "b_points": cnt(winner=b) + 0.5 * cnt(winner=""),
            "a_white_w": cnt(white=a, winner=a), "a_white_l": cnt(white=a, winner=b),
            "a_white_d": cnt(white=a, winner=""),
            "a_black_w": cnt(black=a, winner=a), "a_black_l": cnt(black=a, winner=b),
            "a_black_d": cnt(black=a, winner=""),
            "avg_plies": sum(g["plies"] for g in gs) / len(gs),
            "checkmates": cnt(termination="checkmate"),
            "a_nodes_per_move": na, "b_nodes_per_move": nb,
            "a_sec_per_move": ta, "b_sec_per_move": tb,
        })
    return out


# ------------------------------------------------------------------ writing --
def write_csv(path: Path, rows: List[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def write_workbook(path: Path, runs, games, agent_games, moves, settings: Dict[str, str]):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, Reference, Series
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    base = Font(name=FONT, size=10)
    bold = Font(name=FONT, size=10, bold=True)
    head_font = Font(name=FONT, size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=HEADER_FILL)
    title_font = Font(name=FONT, size=14, bold=True)
    accent = PatternFill("solid", fgColor="FBE3D1")
    thin = Side(style="thin", color="D0CCC6")

    def header(ws, row, labels, col=1):
        for j, label in enumerate(labels):
            c = ws.cell(row=row, column=col + j, value=label)
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 30

    def table_sheet(ws, rows, widths=None):
        cols = list(rows[0])
        header(ws, 1, cols)
        for i, r in enumerate(rows, start=2):
            for j, k in enumerate(cols, start=1):
                c = ws.cell(row=i, column=j, value=r[k])
                c.font = base
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
        for j, k in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(j)].width = (widths or {}).get(
                k, max(9, min(28, len(k) + 2)))
        return {k: get_column_letter(j) for j, k in enumerate(cols, start=1)}, len(rows) + 1

    # ---- raw sheets first (summary formulas point at them) ----
    ws_games = wb.active
    ws_games.title = "Games"
    gcol, glast = table_sheet(ws_games, games, {
        "match": 24, "named_opening": 26, "opening_plies_san": 22, "first_12_plies": 46,
        "white": 12, "black": 12, "winner": 12, "loser": 12, "termination": 20})
    ws_ag = wb.create_sheet("AgentGames")
    acol, alast = table_sheet(ws_ag, agent_games, {"match": 24, "agent": 12, "opponent": 12})
    ws_moves = wb.create_sheet("Moves")
    table_sheet(ws_moves, moves, {"match": 24, "fen_after": 60})

    def G(col):
        return f"Games!${gcol[col]}$2:${gcol[col]}${glast}"

    def A(col):
        return f"AgentGames!${acol[col]}$2:${acol[col]}${alast}"

    # ---- Summary ----
    ws = wb.create_sheet("Summary", 0)
    ws["A1"] = "Match results"
    ws["A1"].font = title_font
    ws["A2"] = ("Scoreline per matchup. Formulas count the Games sheet; A = first agent "
                "named, colours alternate every game.")
    ws["A2"].font = Font(name=FONT, size=9, italic=True, color="666666")
    cols = ["Matchup", "Agent A", "Agent B", "Depth A", "Depth B", "Games",
            "A wins", "B wins", "Draws", "A points", "B points", "A score %",
            "A as White (W)", "A as White (L)", "A as White (D)",
            "A as Black (W)", "A as Black (L)", "A as Black (D)",
            "Avg length (plies)", "Checkmates",
            "A nodes/move", "B nodes/move", "A sec/move", "B sec/move"]
    header(ws, 4, cols)
    for i, run in enumerate(runs, start=5):
        m, a, b = f"$A{i}", f"$B{i}", f"$C{i}"
        ws.cell(row=i, column=1, value=run["match"])
        ws.cell(row=i, column=2, value=run["a"])
        ws.cell(row=i, column=3, value=run["b"])
        ws.cell(row=i, column=4, value=run["summary"]["depth_a"])
        ws.cell(row=i, column=5, value=run["summary"]["depth_b"])
        f = {
            6: f'=COUNTIFS({G("match")},{m})',
            7: f'=COUNTIFS({G("match")},{m},{G("winner")},{a})',
            8: f'=COUNTIFS({G("match")},{m},{G("winner")},{b})',
            9: f'=F{i}-G{i}-H{i}',
            10: f'=G{i}+0.5*I{i}',
            11: f'=H{i}+0.5*I{i}',
            12: f'=IF(F{i}=0,0,J{i}/F{i})',
            13: f'=COUNTIFS({G("match")},{m},{G("white")},{a},{G("winner")},{a})',
            14: f'=COUNTIFS({G("match")},{m},{G("white")},{a},{G("winner")},{b})',
            15: f'=COUNTIFS({G("match")},{m},{G("white")},{a})-M{i}-N{i}',
            16: f'=COUNTIFS({G("match")},{m},{G("black")},{a},{G("winner")},{a})',
            17: f'=COUNTIFS({G("match")},{m},{G("black")},{a},{G("winner")},{b})',
            18: f'=COUNTIFS({G("match")},{m},{G("black")},{a})-P{i}-Q{i}',
            19: f'=AVERAGEIFS({G("plies")},{G("match")},{m})',
            20: f'=COUNTIFS({G("match")},{m},{G("termination")},"checkmate")',
            21: (f'=IFERROR(SUMIFS({A("total_nodes")},{A("match")},{m},{A("agent")},{a})'
                 f'/SUMIFS({A("searched_moves")},{A("match")},{m},{A("agent")},{a}),0)'),
            22: (f'=IFERROR(SUMIFS({A("total_nodes")},{A("match")},{m},{A("agent")},{b})'
                 f'/SUMIFS({A("searched_moves")},{A("match")},{m},{A("agent")},{b}),0)'),
            23: (f'=IFERROR(SUMIFS({A("total_time_s")},{A("match")},{m},{A("agent")},{a})'
                 f'/SUMIFS({A("searched_moves")},{A("match")},{m},{A("agent")},{a}),0)'),
            24: (f'=IFERROR(SUMIFS({A("total_time_s")},{A("match")},{m},{A("agent")},{b})'
                 f'/SUMIFS({A("searched_moves")},{A("match")},{m},{A("agent")},{b}),0)'),
        }
        for col, formula in f.items():
            ws.cell(row=i, column=col, value=formula)
        for col in range(1, len(cols) + 1):
            c = ws.cell(row=i, column=col)
            c.font = base
            c.border = Border(bottom=thin)
            c.number_format = {10: "0.0", 11: "0.0", 12: "0.0%", 19: "0.0", 21: "#,##0",
                               22: "#,##0", 23: "0.00", 24: "0.00"}.get(col, "General")
        ws.cell(row=i, column=12).fill = accent
    sum_last = 4 + len(runs)
    ws.column_dimensions["A"].width = 26
    for col in range(2, len(cols) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 11 if col > 3 else 13
    ws.freeze_panes = "B5"

    chart = BarChart()
    chart.type = "bar"
    chart.title = "Agent A score % by matchup"
    chart.y_axis.title = "Score %"
    chart.y_axis.number_format = "0%"
    chart.y_axis.scaling.min = 0
    chart.y_axis.scaling.max = 1
    chart.add_data(Reference(ws, min_col=12, min_row=4, max_row=sum_last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=5, max_row=sum_last))
    chart.legend = None
    chart.roundedCorners = False
    chart.title.overlay = False
    chart.y_axis.title.overlay = False
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.series[0].graphicalProperties.solidFill = ORANGE
    chart.height, chart.width = 7.5, 16
    ws.add_chart(chart, f"A{sum_last + 3}")

    # ---- Agent Stats (style fingerprint) ----
    ws2 = wb.create_sheet("Agent Stats", 1)
    ws2["A1"] = "Per-agent results and style"
    ws2["A1"].font = title_font
    ws2["A2"] = ("Per game averages from the AgentGames sheet. Rows with an opponent are "
                 "one matchup; the 'All opponents' block combines every game.")
    ws2["A2"].font = Font(name=FONT, size=9, italic=True, color="666666")
    scols = ["Agent", "Opponent", "Games", "Wins", "Losses", "Draws", "Points", "Score %",
             "Wins as White", "Wins as Black", "Avg captures", "Avg checks",
             "Avg material captured (cp)", "Avg material drops", "Avg sacrifices",
             "Castled %", "Avg castle ply", "Avg first check ply", "Avg king moves",
             "Avg book moves", "Nodes/move", "Sec/move", "Avg depth", "Avg eval (own view)"]
    header(ws2, 4, scols)
    pairs = []
    for run in runs:
        pairs.append((run["a"], run["b"]))
        pairs.append((run["b"], run["a"]))
    agents = []
    for run in runs:
        for name in (run["a"], run["b"]):
            if name not in agents:
                agents.append(name)
    rows = [(a, o) for a, o in pairs] + [(a, None) for a in agents]

    def crit(r, opp):
        c = f'{A("agent")},$A{r}'
        return c + (f',{A("opponent")},$B{r}' if opp else "")

    for i, (agent, opp) in enumerate(rows, start=5):
        ws2.cell(row=i, column=1, value=agent)
        ws2.cell(row=i, column=2, value=opp if opp else "All opponents")
        c = crit(i, opp)

        def avg(col):
            return f'=IFERROR(AVERAGEIFS({A(col)},{c}),0)'

        def per_move(num, den="searched_moves"):
            return f'=IFERROR(SUMIFS({A(num)},{c})/SUMIFS({A(den)},{c}),0)'
        f = {
            3: f'=COUNTIFS({c})',
            4: f'=COUNTIFS({c},{A("result")},"W")',
            5: f'=COUNTIFS({c},{A("result")},"L")',
            6: f'=COUNTIFS({c},{A("result")},"D")',
            7: f'=SUMIFS({A("points")},{c})',
            8: f'=IF(C{i}=0,0,G{i}/C{i})',
            9: f'=COUNTIFS({c},{A("result")},"W",{A("colour")},"White")',
            10: f'=COUNTIFS({c},{A("result")},"W",{A("colour")},"Black")',
            11: avg("captures"), 12: avg("checks"), 13: avg("material_captured_cp"),
            14: avg("material_drops"), 15: avg("sacrifices"),
            16: f'=IF(C{i}=0,0,COUNTIFS({c},{A("castled")},"yes")/C{i})',
            17: f'=IFERROR(AVERAGEIFS({A("castle_ply")},{c},{A("castled")},"yes"),"-")',
            18: f'=IFERROR(AVERAGEIFS({A("first_check_ply")},{c},{A("first_check_ply")},">0"),"-")',
            19: avg("king_moves"), 20: avg("book_moves"),
            21: per_move("total_nodes"), 22: per_move("total_time_s"),
            23: per_move("depth_sum"), 24: per_move("eval_sum_own"),
        }
        for col, formula in f.items():
            ws2.cell(row=i, column=col, value=formula)
        for col in range(1, len(scols) + 1):
            cell = ws2.cell(row=i, column=col)
            cell.font = bold if opp is None and col <= 2 else base
            cell.border = Border(bottom=thin)
            if opp is None:
                cell.fill = accent
            cell.number_format = {
                7: "0.0", 8: "0.0%", 11: "0.0", 12: "0.0", 13: "#,##0", 14: "0.00",
                15: "0.00", 16: "0%", 17: "0.0", 18: "0.0", 19: "0.0", 20: "0.0",
                21: "#,##0", 22: "0.00", 23: "0.00", 24: "#,##0"}.get(col, "General")
    st_last = 4 + len(rows)
    ws2.column_dimensions["A"].width = 13
    ws2.column_dimensions["B"].width = 15
    for col in range(3, len(scols) + 1):
        ws2.column_dimensions[get_column_letter(col)].width = 11
    ws2.freeze_panes = "C5"

    # Style chart: captures / checks per game for the 'All opponents' rows.
    first_all = 5 + len(pairs)
    style = BarChart()
    style.type = "col"
    style.title = "Style fingerprint (per game, all opponents)"
    style.y_axis.title = "Per game"
    for col in (11, 12, 14, 15):
        s = Series(Reference(ws2, min_col=col, min_row=first_all, max_row=st_last),
                   title=scols[col - 1])
        style.series.append(s)
    style.set_categories(Reference(ws2, min_col=1, min_row=first_all, max_row=st_last))
    style.roundedCorners = False
    style.title.overlay = False
    style.y_axis.title.overlay = False
    style.legend.overlay = False
    style.x_axis.delete = False
    style.y_axis.delete = False
    palette = [ORANGE, "4E4A45", "B5651D", "9C9389"]
    for s, colour in zip(style.series, palette):
        s.graphicalProperties.solidFill = colour
    style.height, style.width = 8, 18
    ws2.add_chart(style, f"A{st_last + 3}")

    # ---- Notes ----
    wn = wb.create_sheet("Notes")
    wn["A1"] = "How these results were produced"
    wn["A1"].font = title_font
    r = 3
    for k, v in settings.items():
        wn.cell(row=r, column=1, value=k).font = bold
        wn.cell(row=r, column=2, value=v).font = base
        r += 1
    r += 1
    wn.cell(row=r, column=1, value="Column definitions").font = bold
    r += 1
    for k, v in DEFINITIONS:
        wn.cell(row=r, column=1, value=k).font = bold
        cell = wn.cell(row=r, column=2, value=v)
        cell.font = base
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    wn.column_dimensions["A"].width = 28
    wn.column_dimensions["B"].width = 110

    wb.calculation.fullCalcOnLoad = True
    wb.save(path)


DEFINITIONS = [
    ("A / B", "Agent A is the first agent named in the match command (--a), B the second. "
              "Colours alternate every game (A is White in games 1, 3, 5, ...), so each agent "
              "plays half of every matchup with each colour."),
    ("Score % / points", "Win = 1, draw = 0.5, loss = 0."),
    ("Searched moves", "Moves the agent chose by minimax search (depth > 0). Opening-phase "
                       "and book moves are excluded from nodes/sec/depth averages."),
    ("Book moves", "Aggression moves that came from its gambit opening book."),
    ("Named opening", "Deepest recognised named line reached in the game (King's Gambit, "
                      "Elephant, Alien, Martian, Smith-Morra, ...). Blank = none of the list."),
    ("Material captured (cp)", "Total value of enemy material this agent captured "
                               "(P 100, N 320, B 330, R 500, Q 900)."),
    ("Material drops", "Agent moves after which its material balance, measured after the "
                       "opponent's reply, was at least 2 pawns (200 cp) worse than before."),
    ("Sacrifices", "Material drops where the agent's own search score still rated its "
                   "position at least 1.5 pawns better than the material balance, i.e. it "
                   "judged the material was worth giving up. Other drops are mostly blunders "
                   "or forced losses."),
    ("Eval (own view)", "Agent's search score converted to its own perspective "
                        "(positive = it thinks it is better), centipawns; mate ~ 100000, "
                        "so a game containing a forced mate dominates the average."),
    ("Score / eval columns in Moves", "White's perspective, centipawns (positive = good for "
                                      "White). Blank for opening moves."),
    ("material_after / material_net_2ply", "Material balance after the move (White's view) "
                                           "and the mover's net material change over its "
                                           "move plus the opponent's reply."),
    ("Sec/move", "Wall-clock search time. The matchups ran in parallel on one machine, so "
                 "absolute times are inflated; compare agents within a matchup."),
]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folders", nargs="*", help="match log folders (default: match_logs/report/*)")
    p.add_argument("--out", default="match_logs/report/match_report.xlsx")
    p.add_argument("--note", action="append", default=[],
                   help="extra 'key=value' line for the Notes sheet (repeatable)")
    args = p.parse_args()

    folders = [Path(f) for f in args.folders] or sorted(
        d for d in Path("match_logs/report").iterdir() if (d / "games.json").exists())
    runs = load_runs(folders)
    order = {"Material": 0, "Random": 1}
    runs.sort(key=lambda r: (order.get(r["a"], 2), r["match"]))

    games, agent_games, moves = [], [], []
    for run in runs:
        for g in run["games"]:
            grow, arows, mrows = analyse_game(run, g)
            games.append(grow)
            agent_games.extend(arows)
            moves.extend(mrows)
    summary = summary_rows(runs, games, agent_games)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(out.parent / "report_games.csv", games)
    write_csv(out.parent / "report_agent_games.csv", agent_games)
    write_csv(out.parent / "report_moves.csv", moves)
    write_csv(out.parent / "report_summary.csv", summary)

    settings = {"Runs": ", ".join(f.name for f in folders)}
    for note in args.note:
        k, _, v = note.partition("=")
        settings[k.strip()] = v.strip()
    write_workbook(out, runs, games, agent_games, moves, settings)
    for s in summary:
        print(f"{s['match']:<26s} A {s['a_wins']} - {s['b_wins']} B  draws {s['draws']}  "
              f"(A as White {s['a_white_w']}-{s['a_white_l']}-{s['a_white_d']}, "
              f"as Black {s['a_black_w']}-{s['a_black_l']}-{s['a_black_d']})")
    print(f"Wrote {out} and CSVs in {out.parent}")


if __name__ == "__main__":
    main()
