# Match openings, agent identity, and determinism

This note explains how `match.py` handles openings and what the recent change
means for match comparisons.

## What changed

Previously, `match.py` generated one opening with Agent A playing White and
Agent B playing Black, then replayed that same line in the next game with the
colors swapped. This controlled the opening between a color-swapped pair, but
the second game's opening choices had been generated for the opposite agent
identities.

Now, each game gets its own opening generated with the agents assigned to White
and Black in that game. The existing agent-guided selection remains: minimax
agents search for strong moves and may vary among near-best choices within the
configured margin. Agents can also provide their own opening-move hook. No
agent changes are required.

This removes **forced reuse** of an opening between color-swapped games. It
does not guarantee that every opening will be unique: two independent
selections can happen to produce the same moves.

## What `--opening-plies` means

- `--opening-plies 0`: no moves are preselected. Each game starts from the
  standard starting position, and the agents choose their first moves through
  normal gameplay search.
- `--opening-plies N` for `N > 0`: `match.py` selects up to `N` half-moves
  before normal gameplay begins, using the agents assigned to the colors in
  that game. These moves are recorded as opening moves in the game log.

The CLI currently defaults to four opening half-moves; the Python
`run_match()` API defaults to zero. Set the option explicitly when running a
match to avoid relying on different defaults:

```powershell
python match.py --a structure --b material --games 10 --opening-plies 4 --seed 17
python match.py --a structure --b material --games 10 --opening-plies 0 --seed 17
```

## Determinism

The opening selection uses seeded pseudo-randomness. With the same seed, game
count, settings, and freshly initialized agents with the same RNG seeds, the
generated openings are reproducible; rerunning with the same seed does not
intentionally create new openings. Use another seed to get another reproducible
sample. A different seed will usually produce different openings, but does not
mathematically guarantee that every line will differ.

With zero opening plies, seeded randomness can still affect normal play. A
minimax agent may randomly choose among equally best moves, and a Random agent
uses its own seeded move selection. The CLI passes its seed to the agents as
well as the opening generator. For Python callers that construct agents
themselves, agent RNG seeds are set when those agents are created; the
`run_match(seed=...)` argument controls opening selection.

The search time limit is a separate consideration. Under system load, a
time-limited search can occasionally complete a different depth, which can
change the selected move even with the same seed. To compare a fixed depth
without a time cap, use `--time-limit 0`, noting that deeper searches can take
much longer.

## Match-report tradeoff

Fresh per-game openings better preserve each agent's identity when colors
alternate, but color-swapped games no longer form strict same-opening pairs.
That adds opening variation to the results. Opening search also runs once per
game instead of once per color-swapped pair, so matches with opening plies
enabled may take longer; that opening-generation time is not included in the
normal game-move timing statistics.

If a report needs strict control of the opening across color-swapped games,
the current behavior does not offer a reuse option. It would require adding a
paired-opening mode. Setting `--opening-plies 0` makes every game start from
the same standard position, but the agents then play their own opening moves
normally.
