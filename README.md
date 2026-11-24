# Chess agents (COMP3220) - shared engine, match harness, agent plug-ins

## Setup
    pip install -r requirements.txt     # installs python-chess (package name: chess)
    python -m unittest discover -v      # run the full test suite

## Layout
    engine/
      evaluation.py   EvalFn type, shared piece values, material(), MATE_SCORE
      search.py       minimax + alpha-beta, quiescence, transposition table, move ordering
      agent.py        Player / HumanPlayer / Agent / MinimaxAgent / RandomAgent
      game.py         Game controller (what the GUI and match harness talk to)
    agents/
      __init__.py     agent registry (create_agent, available_agents)
      material_agent.py   baseline reference agent
      structure_agent.py  positional/defensive evaluation agent
      template_agent.py   copy this to start a new agent
    gui/              tkinter desktop GUI (python -m gui)
    match.py          agent-vs-agent match harness + logging (CLI)
    pruning_report.py nodes visited with/without alpha-beta (for the docs)
    tests/            unit tests

## Evaluation convention
An evaluation function is `evaluate(board) -> float` and scores from **White's
perspective** (positive = good for White; for Black features compute
`white_value - black_value`). It is only called on non-terminal positions: mate,
stalemate and draws are handled inside the search. Never push/pop on the board.

## Adding your agent (2 steps)
1. Copy `agents/template_agent.py` to `agents/<yours>_agent.py`; set `NAME`,
   `DESCRIPTION`, `DEFAULT_DEPTH` and write `evaluate`.
2. Add one line to `agents/__init__.py`:
   `register_eval_agent("yours", yours_agent)`

It then works in `match.py --a yours`, and shows up in `available_agents()` for the GUI menu.

## Running matches
    python match.py --list
    python match.py --a material --b random --games 6 --depth 3
    python match.py --a structure --b aggression --games 10 --depth-a 3 --depth-b 3 --seed 1
Colours alternate every game. `--time-limit` (default 5 seconds) caps each
searched move; iterative deepening returns the best move from the last fully
completed depth (or a legal fallback if depth 1 cannot finish). Set
`--time-limit 0` for an unlimited search.
`--opening-plies` (CLI default 4; `run_match()` default 0) selects that many
initial half-moves by searching with each bot's evaluation and randomizing among
near-best moves. `--opening-margin-cp` (default 50) controls how far below the
best score a move can be to qualify. A fresh opening is generated for every
game using the agents assigned White and Black in that game. The seed makes
the selected openings reproducible; color-swapped games may use different
opening lines.
Logs go to `match_logs/<time>_<A>_vs_<B>/`: `summary.txt` (scoreline + search
stats), `moves.csv` (every move with score/depth/nodes/time), `games.json`, `games.pgn`.

## GUI
Desktop GUI built with tkinter (standard library, no extra dependencies). From the
project root:

    python -m gui

* **Play vs Agent**: pick an opponent (every agent in `available_agents()`, including
  Random), your colour (White / Random / Black), and its depth (1-5) and thinking-time
  cap. Click a piece and then a target square, or drag it. Castling and en passant are
  normal king / pawn moves; promotion opens a piece chooser. The board flips when you
  play Black.
* **Agent vs Agent**: pick both agents and their settings, then **Step** one move at a
  time or **Auto-play** / **Pause** with a delay between moves.
* Difficulty can also be changed mid-game from the side panel (it sets `agent.depth`
  and `agent.time_limit_s`, effective on the agent's next move). There is always a time
  cap, so the window never freezes during a search.
* Side panel: move list, last search per agent (eval in pawns from White's point of view,
  depth completed, nodes, time), New Game, Undo, Flip, Resign.
* Shortcuts: Ctrl+N new game, Ctrl+Z undo, F flip, Space auto-play, Right arrow step,
  Esc cancel.

Code lives in `gui/`: `app.py` (window + controller), `board_view.py` (board canvas,
input, promotion chooser, result banner), `side_panel.py`, `setup_panel.py`,
`player_bar.py`, `eval_bar.py`, `runner.py` (runs searches on a worker thread; the board
is only changed on the UI thread). `tests/test_gui_smoke.py` drives the GUI without a
main loop (skipped when no display is available).

## Building the GUI on top (API in engine/game.py)
    from engine import Game, HumanPlayer
    from agents import create_agent, available_agents

    game = Game(HumanPlayer("You"), create_agent("structure", depth=3))
    game.board                       # python-chess Board: draw from this
    game.last_move                   # highlight
    game.legal_moves_from(square)    # highlight targets after a click
    move = game.move_from_squares(src, dst)   # None if illegal; auto-queens
    game.play_move(move)             # human move
    game.is_human_turn / game.is_agent_turn
    game.play_agent_move()           # BLOCKS while searching -> run in a thread
    game.is_over, game.result, game.status_text()
    game.undo(); game.on_move = callback

* Agent-vs-agent: `Game(create_agent("a"), create_agent("b"))`, then call
  `play_agent_move()` per timer tick or "Next move" press.
* Difficulty selector: `agent.depth = 2` (a plain attribute, changeable any time).
* Agents search a copy of the board, so the GUI can keep drawing `game.board`
  while a worker thread is thinking. Only apply the finished move on the UI thread.
* Typical depths in pure Python: 3 is fast, 4 is slower, 5+ is impractical
  without a time cap. `find_best_move(..., time_limit_s=...)` uses iterative
  deepening and reports the completed depth in `SearchResult.depth`.
