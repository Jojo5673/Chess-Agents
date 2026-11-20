# Chess agents (COMP3220) - shared engine, match harness, agent plug-ins

DRAFT README for the engine + match half of the project. Add the GUI section and
the "who built which agent" statement once those exist.

## Setup
    pip install -r requirements.txt     # installs python-chess (package name: chess)
    python -m unittest discover -v      # 18 tests, should all pass

## Layout
    engine/
      evaluation.py   EvalFn type, shared piece values, material(), MATE_SCORE
      search.py       minimax + alpha-beta, move ordering, terminal detection
      agent.py        Player / HumanPlayer / Agent / MinimaxAgent / RandomAgent
      game.py         Game controller (what the GUI and match harness talk to)
    agents/
      __init__.py     agent registry (create_agent, available_agents)
      material_agent.py   baseline reference agent
      template_agent.py   copy this to start a new agent
    match.py          agent-vs-agent match harness + logging (CLI)
    pruning_report.py nodes visited with/without alpha-beta (for the docs)
    tests/            unit tests

## The one convention to agree on
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
Colours alternate every game. The first `--opening-plies` (default 4) half-moves
are random but seeded; each opening is used twice with colours swapped. Without
this, two deterministic agents would replay the same game every time.
Logs go to `match_logs/<time>_<A>_vs_<B>/`: `summary.txt` (scoreline + search
stats), `moves.csv` (every move with score/depth/nodes/time), `games.json`, `games.pgn`.

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
* Typical depths in pure Python: 3 is fast, 4 is slower, 5+ is impractical.
