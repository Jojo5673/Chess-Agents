# Chess Agents Project Handoff

This note is for the agent that originally helped establish the project and its
explainer. It records the user goals, investigations, implemented changes, and
current caveats so follow-up work can continue without repeating the history.

## Project context

This is a Python chess-agent project using `python-chess`. The shared engine
and controller are in [engine/](./engine/); agents are registered in
[agents/](./agents/); [match.py](./match.py) runs matches and writes PGN, JSON,
CSV, and summary logs. The original project overview is [README.md](./README.md).

The evaluation convention is White-perspective centipawns: positive scores
favor White and negative scores favor Black. Terminal positions are scored by
the search engine, not by each agent's evaluation function.

## User goals and decisions

### Structure evaluation agent

The project gained a positional/defensive `Structure` agent. It combines
material with piece-square tables, phase-aware king placement, pawn structure,
passed pawns, king safety, piece protection, bishop pair, and rook-file terms.
It is registered as `structure` and has feature tests.

Implemented in commit `2b9539a` (`Add evaluation agent that prioritizes
structure and positioning`): [agents/structure_agent.py](./agents/structure_agent.py),
[agents/__init__.py](./agents/__init__.py), and
[tests/test_structure_agent.py](./tests/test_structure_agent.py).

### Material weighting

The user asked whether Structure should value material more. The advice was
that a multiplier changes the balance between material and positional terms,
but does not alter minimax itself; a small Structure-only increase could be
tested, while a large increase risks suppressing positional play. No multiplier
is present in the current code.

History: commit `9104709` briefly added a global `1.5` material multiplier;
commit `e7b3cc6` removed it after it worsened play. The current shared material
score is unscaled in [engine/evaluation.py](./engine/evaluation.py), and
Structure adds that score at its normal weight. Any future experiment should
be Structure-only, modest, and benchmarked over repeated paired openings.

### Draw claims and repetition

Structure had previously repeated moves in a winning position. An initial
attempt treated claimable repetition as a forced search draw, but the desired
behavior was clarified: a bot should not automatically end the game by claiming
a threefold repetition or 50-move draw.

The current policy is consistent between controller and search:

- [engine/game.py](./engine/game.py) uses `claim_draw=False`.
- [engine/search.py](./engine/search.py) treats automatic draws as terminal:
  stalemate, insufficient material, 75 moves, and fivefold repetition.
- Claimable threefold and 50-move draws do not terminate play automatically.

The claim-policy tests are in [tests/test_draw_claims.py](./tests/test_draw_claims.py).
Two Structure tests that expected claims to be forced terminal outcomes were
removed. The earlier game-four draw was a claimable draw by the winning side
while Structure was materially losing; under the current policy it continues
instead of ending on the claim.

Relevant commits: `1f57ee7` (`fix bug with automatic draws`) and `f994b00`
(`remove game ending on claimable draws`).

### Thread-safe board updates

A GUI thread could observe `game.board` while an agent worker was searching or
while a move was only partly applied. `Game.play_move` now computes SAN and
applies the move on a copied board, then swaps in the completed board. This
preserves the visible board as a complete before-or-after position. The
threading regression test is in [tests/test_game_api.py](./tests/test_game_api.py).
This change was included in `1f57ee7`.

### Depth-3/4/5 match analysis

The user asked why Structure appeared to get worse at greater depths. The
reviewed results were:

| Structure depth | Record | Games |
|---|---:|---:|
| 3 | 15 wins, 0 losses | 15 |
| 4 | 14 wins, 1 loss | 15 |
| 5 | 7 wins, 3 losses | 10 |

All games in these runs ended by checkmate. The first ten opening move
sequences were shared across the three runs, but the samples are still small,
and the depth-5 run has fewer games. Search cost rose substantially: roughly
2,044 nodes / 0.39 seconds per move at depth 3, 8,242 / 1.53 seconds at depth
4, and 71,540 / 11.94 seconds at depth 5, with a depth-5 maximum around 151
seconds.

No clear alpha-beta correctness bug was found in the search implementation.
The likely explanation was a combination of small samples, an approximate
static evaluation, and horizon effects: deeper minimax can choose a different
line whose leaf score looks favorable even though tactics continue beyond the
leaf. This was an evidence-based hypothesis, not a proven sole cause.

Specific depth-5 Game 7 analysis:

- At the position before Structure's 18th move, searching the same position
  selected `h4` at depth 3, `Rxe6` at depth 4, and `f4` at depth 5. The depth-5
  choice scored near equal, but the game continued with `...Rxf4` and a strong
  attack.
- After `...Qh4+`, `Qh3` was the only legal reply. The queen loss was forced,
  not a separate blunder at that point.
- The depth-5 search for that decision took about 89 seconds and searched
  approximately 195,000 nodes.

The match logs reviewed were:

- [depth 3 summary](./match_logs/20261120_011324_Structure_vs_Material/summary.txt)
- [depth 4 summary](./match_logs/20261120_012918_Structure_vs_Material/summary.txt)
- [depth 5 summary](./match_logs/20261120_033351_Structure_vs_Material/summary.txt)

### Quiescence search

To address the horizon issue, quiescence search was added to
[engine/search.py](./engine/search.py) in commit `995f279`. At the normal search
horizon it searches captures and promotions; when the side to move is in check,
it searches all legal evasions rather than using a stand-pat score. Alpha-beta
pruning and terminal scoring continue to apply. A four-ply quiescence cap bounds
long checking sequences; at the cap, a checked side still gets one legal
evasion before static evaluation.

Regression coverage in [tests/test_engine.py](./tests/test_engine.py) checks
that the engine sees a recapture before making a losing queen capture, searches
legal check evasions, and preserves alpha-beta/minimax score parity. The parity
tests were adjusted to keep unpruned tactical searches tractable.

The full suite passed after this change: 59 tests in about 25 seconds. The
additional guided-opening tests bring the current suite to **62 tests**; the
latest full run passed in about 25 seconds. `git diff --check` also passed. No
controlled match benchmark after enabling quiescence was completed.

### Agent-guided opening variety

The user noticed implausible opening moves such as `1.h4` and `2.Rh2`. These
were generated by the match harness, not by Structure: `random_opening` chooses
uniformly from legal moves and only rejects an already finished game or a
mate-in-one. Initially the CLI default injected four random half-moves.

The user then changed the CLI default to zero in commit `9f1027c` (`Remove
opening move randomization as default in bot matches`). The current CLI starts
from the normal initial position by default; random opening moves can still be
requested explicitly with `--opening-plies`. A sound weighted repertoire or
opening book was discussed, but not implemented.

The current uncommitted implementation replaces uniform random legal moves
with agent-guided variety:

- `--opening-plies` selects how many initial half-moves use opening selection;
  it defaults to zero.
- For a `MinimaxAgent`, each candidate is scored by its normal depth search and
  evaluation. The chooser samples only moves within `--opening-margin-cp`
  (default 50 centipawns) of the best score for the side to move.
- Candidate scoring performs a full root search for each legal move, so using
  many opening plies at high search depth can add significant runtime.
- The same generated opening is reused for each color-swapped game pair.
- The selection is seeded and reproducible. Agents without a minimax evaluation
  (such as `RandomAgent`) use their own `choose_move` policy for opening plies.

Example: `python match.py --a structure --b material --games 10 --seed 7
--opening-plies 4 --opening-margin-cp 50`.

The CLI, `run_match()` default, help, and [README.md](./README.md) are now
intended to agree on zero opening plies by default. The PGN at
[match_logs/20261120_080916_Structure_vs_Material/games.pgn](./match_logs/20261120_080916_Structure_vs_Material/games.pgn)
predates the CLI-default commit and therefore still begins with randomized
moves.

## Git history references

Relevant commits on the current branch:

- `2b9539a` — add and register Structure evaluation agent.
- `9104709` — temporarily add global material multiplier.
- `e7b3cc6` — remove the global material multiplier.
- `1f57ee7` — copy-and-swap board update; initial automatic-draw work.
- `f994b00` — stop ending games/search on claimable draws.
- `995f279` — add quiescence search and tests.
- `9f1027c` — set the `match.py` CLI opening plies default to zero.

At handoff creation, `9f1027c` was `HEAD` and the worktree had no other
uncommitted code changes. The agent-guided opening selection and its tests are
subsequent work in the current task.

## Suggested follow-up

1. Reconcile the `run_match()` default, CLI help, and README opening-default
   wording.
2. Benchmark Structure after quiescence across more seeds/opening pairs; compare
   equivalent colors and depths rather than relying on a few games.
3. If material weighting is revisited, test a small Structure-only weight
   change against the current unscaled baseline.
4. Benchmark different opening score margins to decide whether 50 centipawns
   gives enough variety without allowing strategically poor choices.
