# Chess-Playing Agents: Minimax with Alpha-Beta Pruning

COMP3220 pair assignment implementing a chess engine and two chess agents, each built on **Minimax with Alpha-Beta pruning**, each with a different playing strategy. They share one search engine, and they can be played against a human or against each other through the desktop GUI, or run head-to-head from the command line to produce match logs.

Pair Members: Joseph Udoudo `(620172690)` and Ruwan Amarakoon `(620171573)`

## Contributions

| Part | Built by |
| --- | --- |
| Shared game engine: search, game controller, agent registry | Joseph Udoudo |
| Match harness, logging, pruning report | Joseph Udoudo |
| Structure agent | Joseph Udoudo |
| Aggression agent | Ruwan Amarakoon |
| Tkinter GUI | Ruwan Amarakoon |
| Documentation | Joseph Udoudo |
| Match report | Ruwan Amarakoon |

Each agent's evaluation function was designed and written independently by its owner. The two
evaluation functions share the material count and no other code.

## The two agents

Both agents run the same search. Only the evaluation function, the part that decides how good a position is, differs.

### Structure: positional and defensive

This agent plays like a patient positional player, prefering well-placed pieces, a healthy pawn structure, protected pieces and a sheltered king, and tries to win slowly by avoiding weaknesses. Its evaluation is material plus piece-square tables (evolve as game progresses), pawn structure (doubled, isolated, backward, passed and protected pawns), king safety (safe corner, pawn shield, open files, king stuck in the centre), piece protection, a bishop pair, and rooks on open files. King-safety terms fade out as pieces leave the board.

### Aggression: attacking

The agent plays for the initiative and will sacrifice material for an attack. Its evaluation is material plus safe mobility, king attack (scored non-linearly, so several attackers together are worth far more than the same pieces spread out), king exposure, threats against enemy pieces by cheaper pieces, development, and centre control. It also carries a small opening book of gambits (King's Gambit, Evans Gambit, Smith-Morra, Elephant, Budapest and others), so in the opening it plays sharp, well-known lines before falling back on search.

| | Structure | Aggression |
| --- | --- | --- |
| Philosophy | Build a sound position, win slowly | Act on initiative, win through threats |
| What it measures | Static properties: placement, pawn formations, shelter | Dynamic properties: mobility, pressure, attacks |
| Pawns | Evaluated in detail | Only pawns in the centre |
| King | Own king safety (shield, castling, open files) | Pressure on the enemy king; exposure of its own |
| Piece activity | Piece-square tables and protection | Mobility and threats |
| Opening | Search | Gambit book, then search |

A full written comparison is in the documentation.

## Requirements and installation

- **Python 3.10 or newer**
- **python-chess**
- **tkinter**

No other dependencies. Run the command to install dependencies.

```bash
pip install -r requirements.txt
```

**Run every command in this README from the project root** (the folder containing `engine/`,
`agents/`, `gui/` and `match.py`).

---

## Running the GUI

```bash
python -m gui
```

The window opens on a new game panel. Choose a mode at the top of the panel:

### Human vs Agent

1. Pick **Play vs Agent**.
2. Pick the **opponent**: Random, Material (baseline bot that only evaluates on material), **Structure** or **Aggression**.
3. Set the agent's **Depth** (1 to 5) and **Think** time (1, 3, 5, 10 or 30 seconds per move).
4. Choose your colour: White, Random or Black (the board flips when you play Black).
5. Press **Play**.

Click a piece and then a target square (legal targets are highlighted), or drag the piece.
Castling is a normal king move (e1 to g1 or c1) and en passant a normal pawn capture. Promotion
opens a piece chooser. The agent replies automatically.

### Agent vs Agent

1. Pick **Agent vs Agent**.
2. Choose the agent for **White** and for **Black** (for example Structure against Aggression), and
   set each one's depth and thinking time.
3. Press **Play**, then either:
   - **Step** to play one move at a time, or
   - **Auto-play** to play the whole game, with an adjustable **Delay** between moves, and
     **Pause** to stop.

### During and after a game

- The **side panel** shows the move list, the last search of each agent (evaluation in pawns from
  White's point of view, depth completed, nodes searched, time taken) and an evaluation bar beside
  the board.
- **Undo**, **Flip** the board, **Resign**, or start a **New** game. After a game ends the Resign
  button becomes **Again**, which offers a rematch with the same agents and settings and an option
  to swap colours.
- **Difficulty can be changed mid-game** from the side panel (depth and thinking time). It takes
  effect on that agent's next move.
- When a game is over you can **review** it move by move with the arrow keys.
- Every search has a time cap, so the window never freezes while an agent thinks. If the cap is
  reached, the agent plays the best move from the deepest search it finished.

| Key | Action |
| --- | --- |
| Ctrl+N | New game |
| Ctrl+Z | Undo |
| F | Flip the board |
| Space | Start / pause auto-play (agent vs agent) |
| Right arrow | Agent vs agent: play one move. In a finished game: step forward through the moves |
| Left arrow | In a finished game, step back through the moves |
| Home / End | In a finished game, jump to the start / the end |
| Esc | Cancel a selection, promotion chooser or result banner |


## Running agent-vs-agent matches from the command line

`match.py` plays a fixed number of games between two agents, **alternates colours every game**,
and writes a full log of every move and result for the match report.

```bash
# show the registered agents
python match.py --list

# running comparison matches with both agents
python match.py --a structure --b aggression --games 10 --depth 3 --seed 1
python match.py --a structure --b aggression --games 10 --depth 3 --time-limit 0 --seed 1

# testing an agent against the baseline
python match.py --a aggression --b material  --games 6  --depth 3     # vs the baseline
python match.py --a structure  --b random    --games 6  --depth 3     # sanity check
```

Agent keys are `random`, `material`, `structure` and `aggression`. **A and B are fixed by the command line**: in `--a structure --b aggression`, Structure is always "A" in the logs.

| Option | Default | Meaning |
| --- | --- | --- |
| `--list` | | List the registered agents and exit |
| `--a KEY`, `--b KEY` | `material`, `random` | The two agents |
| `--games N` | `6` | Number of games. Colours alternate (A is White in games 1, 3, 5, ...) |
| `--depth D` | agent default (3) | Requested search depth for both agents |
| `--depth-a D`, `--depth-b D` | | Depth for A or B (overrides `--depth`) |
| `--time-limit S` | `5` | Maximum seconds per move. `0` = unlimited. See the note below |
| `--opening-plies N` | `4` | Opening half-moves chosen by the agents themselves, with seeded randomness. `0` = start from the normal position |
| `--opening-margin-cp C` | `50` | An opening move may be up to `C` centipawns worse than the best move |
| `--max-plies N` | `300` | Declare a draw after this many half-moves |
| `--seed N` | `0` | Seed for openings and tie-breaking |
| `--out DIR` | `match_logs` | Log folder (`""` to disable logging) |
| `--verbose` | off | Print every move with its score, nodes and time |


**About depth and the time limit.** With a time limit, the engine uses *iterative deepening*: it searches depth 1, then 2, then 3 and so on up to the requested depth, and plays the best move from the last depth it fully completed. The requested depth is therefore a ceiling, and the depth actually reached is recorded for every move. A slower evaluation function reaches a shallower depth in the same time. For a clean comparison of strategies at equal depth, and for exactly repeatable runs, use
`--time-limit 0`.

**About openings.** For the first `--opening-plies` half-moves of every game, the side to move scores each legal move with its own search and evaluation and picks one at random from the moves within `--opening-margin-cp` of the best (the Aggression agent plays moves from its gambit book here when it has one). This gives varied but sensible openings. Each game gets its own seeded opening, and the whole match is reproducible from `--seed`.

### Output

Each run writes a folder `match_logs/<time>_<A>_vs_<B>/` with:

| File | Contents |
| --- | --- |
| `summary.txt` | The scoreline (wins, draws, points), results per colour, average game length, and each agent's average nodes and time per move |
| `moves.csv` | Every move: `game, ply, color, side, player, san, uci, source, score, depth, nodes, time_s` |
| `games.json` | All games and the summary in one structured file |
| `games.pgn` | All games in PGN, which opens in any chess viewer |

Example `summary.txt`:

```
MATCH: A = Structure (depth 3)  vs  B = Material (depth 3)
Games: 2   Scoreline: A 2 - 0 B   Draws: 0   Points: A 2.0 / B 0.0
A as White: 1W-0L-0D    A as Black: 1W-0L-0D
Average game length: 114.5 plies
A (Structure): 111 moves, avg 3840 nodes/move, avg 0.69s/move (max 5.00s)
B (Material): 110 moves, avg 3743 nodes/move, avg 0.31s/move (max 2.42s)

  Game 1: W=Structure  B=Material   1-0      checkmate            67 plies
  Game 2: W=Material   B=Structure  0-1      checkmate            162 plies
```

Notes on the logs:

- `score` is the agent's evaluation from **White's point of view** (positive favours White); a
  forced mate appears as about 100,000.
- `source` is `opening`, `agent` or `human`. Opening-phase rows have no score or search statistics.
- `depth` is the depth **completed** for that move. A move played from the Aggression agent's
  opening book is logged with depth 0 and 0 nodes.
- `match_logs/` is listed in `.gitignore`, so logs are not committed. Copy the runs you use for the
  match report somewhere permanent.

---

To measure how much pruning saves:

```bash
python pruning_report.py --max-depth 3     # nodes with and without pruning and ordering (takes about a minute)
```

The full explanation, with results, is in the documentation.

---

