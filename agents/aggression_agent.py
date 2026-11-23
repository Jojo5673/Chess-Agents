"""
Aggression agent: an attacking, initiative-first player.

Strategic identity
------------------
Where Structure asks "is my position sound?", Aggression asks "how much
pressure am I creating?". Its evaluation rewards:

  * mobility        - safe squares each piece reaches (activity over placement)
  * king attack     - pieces bearing down on the enemy king zone, scored
                      NON-LINEARLY so that several attackers together are worth
                      far more than the same attackers spread out. This is what
                      lets it sacrifice material for a mating attack: a strong
                      enough attack outweighs a pawn or even a minor piece.
  * king exposure   - open lines (diagonals/files/ranks not blocked by its own
                      pawns) leading to a king while the enemy still has
                      attacking pieces. Because scores are zero-sum, this also
                      keeps its OWN king relatively safe: it will not open its
                      own king to win something small.
  * threats         - enemy pieces attacked by cheaper pieces (a pawn hitting a
                      knight, a knight hitting a queen ...). This is how it
                      punishes inaccuracies: loose, overloaded enemy pieces are
                      targets.
  * development     - minor pieces off the back rank, scaled to the opening.
  * centre control  - attacks on, and pawns in, d4/e4/d5/e5.

None of these reuse Structure's terms (piece-square tables, pawn structure,
pawn shields, bishop pair, rook files, defended/hanging pieces).

It also carries a small opening book of popular gambits (see BOOK_LINES), so
in the opening it plays sharp, well-known lines instead of whatever a shallow
search prefers. Out of book it is a normal minimax/alpha-beta agent.

Scores follow the project convention: White's perspective, centipawns.
"""
import random
import time
from typing import Dict, List, Optional, Tuple

import chess

from engine.agent import MinimaxAgent
from engine.evaluation import PIECE_VALUES, material
from engine.search import SearchResult

NAME = "Aggression"
DESCRIPTION = (
    "Attacking gambiteer: plays sharp gambits, values mobility, threats and "
    "king attacks over material, and will sacrifice for a strong attack."
)
DEFAULT_DEPTH = 3

# ---- tunable weights --------------------------------------------------------
# Safe-mobility bonus per reachable square, by piece type.
MOBILITY_WEIGHTS = {chess.KNIGHT: 4, chess.BISHOP: 4, chess.ROOK: 2, chess.QUEEN: 1}

# King attack. Each piece that hits the enemy king zone adds its weight in
# "attack units"; every attacked zone square adds one more unit. The score is
# KING_ATTACK_SCALE * units^2, capped, and only applies with 2+ attackers.
KING_ATTACK_UNITS = {chess.PAWN: 1, chess.KNIGHT: 2, chess.BISHOP: 2,
                     chess.ROOK: 3, chess.QUEEN: 5}
KING_ATTACK_SCALE = 2.5
KING_ATTACK_CAP = 500
LONE_ATTACKER_BONUS = 6          # per unit when only one piece attacks
NO_QUEEN_ATTACK_FACTOR = 0.5     # attacks are much weaker without a queen

# King exposure: squares a queen standing on the king would see, ignoring
# everything except the king's own pawns. Scaled by the enemy's attacking force.
KING_EXPOSURE_WEIGHT = 3

# Threats: enemy piece attacked by a cheaper piece.
THREAT_FRACTION = 0.15           # bonus = fraction * (victim - attacker value)

# Development: penalty per minor piece still on its back rank (opening only).
UNDEVELOPED_MINOR_PENALTY = 18

# Centre control.
CENTRE_ATTACK_BONUS = 4          # per attack on d4/e4/d5/e5
CENTRE_PAWN_BONUS = 12           # per own pawn on d4/e4/d5/e5

MAX_PHASE = 24
_PHASE_VALUES = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}

# ---- precomputed masks ------------------------------------------------------
_CENTRE = chess.BB_D4 | chess.BB_E4 | chess.BB_D5 | chess.BB_E5
_BACK_RANK = {chess.WHITE: chess.BB_RANK_1, chess.BLACK: chess.BB_RANK_8}
_KING_ZONE = tuple(chess.BB_KING_ATTACKS[sq] | chess.BB_SQUARES[sq] for sq in chess.SQUARES)
_ATTACKERS = (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)


def _pawn_attacks(pawns: int, color: chess.Color) -> int:
    if color == chess.WHITE:
        return (((pawns << 7) & ~chess.BB_FILE_H) | ((pawns << 9) & ~chess.BB_FILE_A)) & chess.BB_ALL
    return ((pawns >> 9) & ~chess.BB_FILE_H) | ((pawns >> 7) & ~chess.BB_FILE_A)


def _queen_rays(square: int, occupied: int) -> int:
    """Squares a queen on `square` attacks given `occupied` blockers."""
    return (chess.BB_DIAG_ATTACKS[square][chess.BB_DIAG_MASKS[square] & occupied]
            | chess.BB_FILE_ATTACKS[square][chess.BB_FILE_MASKS[square] & occupied]
            | chess.BB_RANK_ATTACKS[square][chess.BB_RANK_MASKS[square] & occupied])


def game_phase(board: chess.Board) -> int:
    """Remaining non-pawn material: 24 = opening, 0 = bare kings and pawns."""
    phase = 0
    for piece_type, value in _PHASE_VALUES.items():
        phase += value * chess.popcount(board.pieces_mask(piece_type, chess.WHITE)
                                        | board.pieces_mask(piece_type, chess.BLACK))
    return min(MAX_PHASE, phase)


class _SideInfo:
    """Attack data for one colour, computed once per evaluation."""
    __slots__ = ("pawn_attacks", "piece_attacks", "all_attacks")

    def __init__(self, board: chess.Board, color: chess.Color):
        self.pawn_attacks = _pawn_attacks(board.pieces_mask(chess.PAWN, color), color)
        # (piece_type, square, attack mask) for every non-pawn, non-king piece
        self.piece_attacks: List[Tuple[int, int, int]] = []
        all_attacks = self.pawn_attacks
        for piece_type in _ATTACKERS:
            for sq in chess.scan_forward(board.pieces_mask(piece_type, color)):
                mask = board.attacks_mask(sq)
                self.piece_attacks.append((piece_type, sq, mask))
                all_attacks |= mask
        self.all_attacks = all_attacks


# ---- features (each returns a score for ONE side; evaluate subtracts) ------
def mobility(board: chess.Board, color: chess.Color, us: _SideInfo, them: _SideInfo) -> int:
    """Squares reachable that are not own-occupied and not hit by enemy pawns."""
    blocked = board.occupied_co[color] | them.pawn_attacks
    return sum(MOBILITY_WEIGHTS[pt] * chess.popcount(mask & ~blocked)
               for pt, _, mask in us.piece_attacks)


def king_attack(board: chess.Board, color: chess.Color, us: _SideInfo) -> float:
    """Pressure `color` puts on the ENEMY king zone (non-linear in attackers)."""
    enemy_king = board.king(not color)
    if enemy_king is None:
        return 0.0
    zone = _KING_ZONE[enemy_king]
    units = 0
    attackers = 0
    hit = us.pawn_attacks & zone
    if hit:
        units += KING_ATTACK_UNITS[chess.PAWN]
    for pt, _, mask in us.piece_attacks:
        if mask & zone:
            attackers += 1
            units += KING_ATTACK_UNITS[pt]
            hit |= mask & zone
    units += chess.popcount(hit)
    if attackers >= 2:
        score = min(KING_ATTACK_CAP, KING_ATTACK_SCALE * units * units)
    else:
        score = LONE_ATTACKER_BONUS * units
    if not board.pieces_mask(chess.QUEEN, color):
        score *= NO_QUEEN_ATTACK_FACTOR
    return score


def king_exposure(board: chess.Board, color: chess.Color) -> float:
    """How open `color`'s OWN king is, weighted by the enemy's attacking force."""
    king = board.king(color)
    if king is None:
        return 0.0
    own_pawns = board.pieces_mask(chess.PAWN, color)
    lines = chess.popcount(_queen_rays(king, own_pawns))
    enemy_force = 0
    for piece_type, value in _PHASE_VALUES.items():
        enemy_force += value * chess.popcount(board.pieces_mask(piece_type, not color))
    return KING_EXPOSURE_WEIGHT * lines * min(enemy_force, 16) / 16


def threats(board: chess.Board, color: chess.Color, us: _SideInfo) -> float:
    """Enemy pieces attacked by a cheaper piece of ours."""
    total = 0.0
    enemy = not color
    for victim_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        victims = board.pieces_mask(victim_type, enemy)
        if not victims:
            continue
        victim_value = PIECE_VALUES[victim_type]
        # pawns attacking pieces
        total += (THREAT_FRACTION * (victim_value - PIECE_VALUES[chess.PAWN])
                  * chess.popcount(us.pawn_attacks & victims))
        for pt, _, mask in us.piece_attacks:
            gain = victim_value - PIECE_VALUES[pt]
            if gain > 50 and mask & victims:
                total += THREAT_FRACTION * gain * chess.popcount(mask & victims)
    return total


def undeveloped_minors(board: chess.Board, color: chess.Color) -> int:
    minors = board.pieces_mask(chess.KNIGHT, color) | board.pieces_mask(chess.BISHOP, color)
    return chess.popcount(minors & _BACK_RANK[color])


def centre_control(board: chess.Board, color: chess.Color, us: _SideInfo) -> int:
    attacks = chess.popcount(us.pawn_attacks & _CENTRE)
    for _, _, mask in us.piece_attacks:
        attacks += chess.popcount(mask & _CENTRE)
    pawns = chess.popcount(board.pieces_mask(chess.PAWN, color) & _CENTRE)
    return CENTRE_ATTACK_BONUS * attacks + CENTRE_PAWN_BONUS * pawns


def evaluate(board: chess.Board) -> float:
    white = _SideInfo(board, chess.WHITE)
    black = _SideInfo(board, chess.BLACK)
    phase = game_phase(board)
    opening = phase / MAX_PHASE

    score = float(material(board))
    score += mobility(board, chess.WHITE, white, black) - mobility(board, chess.BLACK, black, white)
    score += king_attack(board, chess.WHITE, white) - king_attack(board, chess.BLACK, black)
    score -= king_exposure(board, chess.WHITE) - king_exposure(board, chess.BLACK)
    score += threats(board, chess.WHITE, white) - threats(board, chess.BLACK, black)
    score -= (UNDEVELOPED_MINOR_PENALTY * opening
              * (undeveloped_minors(board, chess.WHITE) - undeveloped_minors(board, chess.BLACK)))
    score += opening * (centre_control(board, chess.WHITE, white)
                        - centre_control(board, chess.BLACK, black))
    return score


# ---- opening book -----------------------------------------------------------
# Each entry: (colour the book plays, weight, SAN line from the start).
# Only the moves of the book's colour are used as book moves; the other side's
# moves just say which position we expect. If the opponent leaves the line, the
# agent falls back to its normal search.
BOOK_LINES: List[Tuple[chess.Color, int, str]] = [
    # --- as White: always 1.e4, then a gambit or sharp system per reply ---
    (chess.WHITE, 3, "e4 e5 f4"),                                  # King's Gambit
    (chess.WHITE, 2, "e4 e5 f4 exf4 Nf3"),
    (chess.WHITE, 2, "e4 e5 f4 d5 exd5"),                          # vs Falkbeer
    (chess.WHITE, 2, "e4 e5 Nf3 Nc6 Bc4 Bc5 b4"),                  # Evans Gambit
    (chess.WHITE, 1, "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5"),                 # Fried Liver try
    (chess.WHITE, 1, "e4 e5 Nf3 Nc6 d4 exd4 Bc4"),                 # Scotch Gambit
    (chess.WHITE, 3, "e4 c5 d4 cxd4 c3"),                          # Smith-Morra Gambit
    (chess.WHITE, 3, "e4 c5 d4 cxd4 c3 dxc3 Nxc3"),
    (chess.WHITE, 3, "e4 c6 d4 d5 Nc3 dxe4 Nxe4"),                 # Caro-Kann ...
    (chess.WHITE, 3, "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Ng5"),         # Alien Gambit
    (chess.WHITE, 3, "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Nf6 Ng5 h6 Nxf7"),
    (chess.WHITE, 3, "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng5 Bg6 N1f3 h6 Ne6"),  # Martian Gambit
    (chess.WHITE, 2, "e4 e6 d4 d5 Nc3"),                           # French
    (chess.WHITE, 2, "e4 d5 exd5 Qxd5 Nc3"),                       # Scandinavian
    (chess.WHITE, 2, "e4 Nf6 e5 Nd5 d4"),                          # Alekhine
    (chess.WHITE, 2, "e4 d6 d4 Nf6 Nc3 g6 f4"),                    # Austrian Attack
    (chess.WHITE, 2, "e4 g6 d4 Bg7 Nc3"),
    (chess.WHITE, 1, "e4 Nc6 d4"),
    # --- as Black ---
    (chess.BLACK, 3, "e4 e5 Nf3 d5"),                              # Elephant Gambit
    (chess.BLACK, 3, "e4 e5 Nf3 d5 exd5 e4"),
    (chess.BLACK, 2, "e4 e5 Nf3 d5 exd5 e4 Qe2 Nf6"),
    (chess.BLACK, 2, "e4 e5 Nf3 d5 exd5 e4 Ne5 Nf6"),
    (chess.BLACK, 3, "e4 e5 Nf3 d5 Nxe5 Bd6"),
    (chess.BLACK, 2, "e4 e5 f4 d5"),                               # Falkbeer Countergambit
    (chess.BLACK, 2, "e4 e5 Bc4 Nf6"),
    (chess.BLACK, 2, "e4 e5 Nc3 Nf6"),
    (chess.BLACK, 2, "e4 e5 d4 exd4"),
    (chess.BLACK, 2, "d4 d5 c4 e5"),                               # Albin Countergambit
    (chess.BLACK, 2, "d4 d5 c4 e5 dxe5 d4"),
    (chess.BLACK, 2, "d4 d5 c4 e5 dxe5 d4 Nf3 Nc6"),
    (chess.BLACK, 2, "d4 Nf6 c4 e5"),                              # Budapest Gambit
    (chess.BLACK, 2, "d4 Nf6 c4 e5 dxe5 Ng4"),
    (chess.BLACK, 1, "d4 d5 Nf3 Nf6"),
    (chess.BLACK, 1, "d4 Nf6 Nf3 g6"),
    (chess.BLACK, 1, "c4 e5"),
    (chess.BLACK, 1, "Nf3 d5"),
]


def _book_key(board: chess.Board) -> str:
    # EPD = placement, side to move, castling, legal en passant (no clocks),
    # so transpositions into a book position are recognised.
    return board.epd()


def _build_book(lines) -> Dict[chess.Color, Dict[str, Dict[chess.Move, int]]]:
    book: Dict[chess.Color, Dict[str, Dict[chess.Move, int]]] = {chess.WHITE: {}, chess.BLACK: {}}
    for color, weight, line in lines:
        board = chess.Board()
        for san in line.split():
            move = board.parse_san(san)   # raises if a line is mistyped
            if board.turn == color:
                entry = book[color].setdefault(_book_key(board), {})
                entry[move] = max(entry.get(move, 0), weight)
            board.push(move)
    return book


BOOK = _build_book(BOOK_LINES)


def book_move(board: chess.Board, rng: random.Random) -> Optional[chess.Move]:
    """A weighted-random book move for the side to move, or None if out of book."""
    entry = BOOK[board.turn].get(_book_key(board))
    if not entry:
        return None
    moves = [m for m in entry if board.is_legal(m)]
    if not moves:
        return None
    return rng.choices(moves, weights=[entry[m] for m in moves])[0]


class AggressionAgent(MinimaxAgent):
    """MinimaxAgent that consults the gambit book before searching."""

    def __init__(self, *args, use_book: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_book = use_book

    def opening_move(self, board: chess.Board, rng: random.Random) -> Optional[chess.Move]:
        """Book hook used by the match harness's opening phase."""
        return book_move(board, rng) if self.use_book else None

    def choose_move(self, board: chess.Board) -> SearchResult:
        if self.use_book:
            start = time.perf_counter()
            move = book_move(board, self.rng)
            if move is not None:
                after = board.copy(stack=False)
                after.push(move)
                return SearchResult(move, self.eval_fn(after), 0, 0,
                                    time.perf_counter() - start)
        return super().choose_move(board)


def create(depth: int = DEFAULT_DEPTH, seed: Optional[int] = None,
           time_limit_s: Optional[float] = None) -> AggressionAgent:
    return AggressionAgent(NAME, evaluate, depth, seed=seed,
                           description=DESCRIPTION, time_limit_s=time_limit_s)
