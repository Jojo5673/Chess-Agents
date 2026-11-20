"""
Structure is a positional, defensive agent.

It prefers well-placed pieces, healthy pawn formations, protected material,
and a sheltered king. It aims to avoid weaknesses and improve steadily rather
than pursuing mobility or direct attacks.
"""
import chess

from engine.evaluation import PIECE_VALUES, material

NAME = "Structure"
DESCRIPTION = (
    "Positional/defensive: piece placement, pawn structure and king safety; "
    "wins slowly by avoiding weaknesses."
)
DEFAULT_DEPTH = 3

DOUBLED_PAWN_PENALTY = 15
ISOLATED_PAWN_PENALTY = 15
BACKWARD_PAWN_PENALTY = 10
PASSED_PAWN_BONUSES = (0, 0, 10, 20, 35, 60, 100, 150)
PASSED_PAWN_ENDGAME_SCALE = 1.5
PROTECTED_PAWN_BONUS = 6
SAFE_KING_BONUS = 30
PAWN_SHIELD_BONUS = 10
OPEN_KING_FILE_PENALTY = 20
CENTRAL_KING_PENALTY = 25
PROTECTED_PIECE_BONUS = 4
HANGING_PIECE_DIVISOR = 10
BISHOP_PAIR_BONUS = 30
ROOK_OPEN_FILE_BONUS = 20
ROOK_SEMI_OPEN_FILE_BONUS = 10
MAX_GAME_PHASE = 24

# Simplified Evaluation Function tables in visual order: rank 8 down to rank 1.
PAWN_TABLE = (
    0, 0, 0, 0, 0, 0, 0, 0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
    5, 5, 10, 25, 25, 10, 5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, -5, -10, 0, 0, -10, -5, 5,
    5, 10, 10, -20, -20, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
KNIGHT_TABLE = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)
BISHOP_TABLE = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)
ROOK_TABLE = (
    0, 0, 0, 5, 5, 0, 0, 0,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    -5, 0, 0, 0, 0, 0, 0, -5,
    5, 10, 10, 10, 10, 10, 10, 5,
    0, 0, 0, 0, 0, 0, 0, 0,
)
QUEEN_TABLE = (
    -20, -10, -10, -5, -5, -10, -10, -20,
    -10, 0, 5, 0, 0, 0, 0, -10,
    -10, 5, 5, 5, 5, 5, 0, -10,
    0, 0, 5, 5, 5, 5, 0, -5,
    -5, 0, 5, 5, 5, 5, 0, -5,
    -10, 0, 5, 5, 5, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -5, -5, -10, -10, -20,
)
KING_MIDDLEGAME_TABLE = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    20, 20, 0, 0, 0, 0, 20, 20,
    20, 30, 10, 0, 0, 10, 30, 20,
)
KING_ENDGAME_TABLE = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)

_TABLES = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
}
_SAFE_KING_SQUARES = {
    chess.WHITE: {chess.B1, chess.C1, chess.G1, chess.H1},
    chess.BLACK: {chess.B8, chess.C8, chess.G8, chess.H8},
}
_BACKWARD_SUPPORT_MASKS = {}
_PASSED_PAWN_MASKS = {}
for _color in (chess.WHITE, chess.BLACK):
    _support_masks = []
    _passed_masks = []
    for _square in chess.SQUARES:
        _file = chess.square_file(_square)
        _rank = chess.square_rank(_square)
        _relative_rank = _rank if _color == chess.WHITE else 7 - _rank
        _support_mask = 0
        _passed_mask = 0
        for _candidate_rank in range(8):
            _candidate_relative_rank = (
                _candidate_rank if _color == chess.WHITE else 7 - _candidate_rank
            )
            for _candidate_file in range(max(0, _file - 1), min(7, _file + 1) + 1):
                _candidate = chess.square(_candidate_file, _candidate_rank)
                if _candidate_file != _file and _candidate_relative_rank <= _relative_rank:
                    _support_mask |= chess.BB_SQUARES[_candidate]
                if _candidate_relative_rank > _relative_rank:
                    _passed_mask |= chess.BB_SQUARES[_candidate]
        _support_masks.append(_support_mask)
        _passed_masks.append(_passed_mask)
    _BACKWARD_SUPPORT_MASKS[_color] = tuple(_support_masks)
    _PASSED_PAWN_MASKS[_color] = tuple(_passed_masks)


def _side_difference(board: chess.Board, score_for_side) -> float:
    """Return one side-local feature as White's score minus Black's."""
    return score_for_side(chess.WHITE) - score_for_side(chess.BLACK)


def game_phase(board: chess.Board) -> int:
    """Calculate remaining non-pawn material phase, capped at 24."""
    phase = 0
    phase_values = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}
    for piece_type, phase_value in phase_values.items():
        phase += len(board.pieces(piece_type, chess.WHITE) | board.pieces(piece_type, chess.BLACK)) * phase_value
    return min(MAX_GAME_PHASE, phase)


def piece_square_score(board: chess.Board) -> float:
    """Score piece placement, blending the king tables by game phase."""
    phase = game_phase(board)
    total = 0.0
    for color in (chess.WHITE, chess.BLACK):
        sign = 1 if color == chess.WHITE else -1
        for piece_type, table in _TABLES.items():
            for square in board.pieces(piece_type, color):
                index = chess.square_mirror(square) if color == chess.WHITE else square
                total += sign * table[index]
        king_square = board.king(color)
        if king_square is not None:
            index = chess.square_mirror(king_square) if color == chess.WHITE else king_square
            mg = KING_MIDDLEGAME_TABLE[index]
            eg = KING_ENDGAME_TABLE[index]
            total += sign * (mg * phase + eg * (MAX_GAME_PHASE - phase)) / MAX_GAME_PHASE
    return total


def doubled_pawns(board: chess.Board) -> float:
    """Penalize each pawn beyond the first on a file."""
    def side_score(color):
        pawns = board.pieces(chess.PAWN, color)
        return -DOUBLED_PAWN_PENALTY * sum(
            max(0, len(pawns & chess.BB_FILES[file_index]) - 1)
            for file_index in range(8)
        )
    return _side_difference(board, side_score)


def isolated_pawns(board: chess.Board) -> float:
    """Penalize pawns whose adjacent files contain no friendly pawns."""
    def side_score(color):
        pawns = board.pieces(chess.PAWN, color)
        score = 0
        for square in pawns:
            file_index = chess.square_file(square)
            adjacent_files = 0
            if file_index > 0:
                adjacent_files |= chess.BB_FILES[file_index - 1]
            if file_index < 7:
                adjacent_files |= chess.BB_FILES[file_index + 1]
            if not pawns & adjacent_files:
                score -= ISOLATED_PAWN_PENALTY
        return score
    return _side_difference(board, side_score)


def backward_pawns(board: chess.Board) -> float:
    """Penalize unsupported pawns whose forward square is blocked or pawn-attacked."""
    def side_score(color):
        pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, not color)
        direction = 1 if color == chess.WHITE else -1
        score = 0
        for square in pawns:
            file_index = chess.square_file(square)
            has_neighbor_support = bool(pawns & _BACKWARD_SUPPORT_MASKS[color][square])
            next_rank = chess.square_rank(square) + direction
            if has_neighbor_support or not 0 <= next_rank < 8:
                continue
            forward_square = chess.square(file_index, next_rank)
            blocked = board.piece_at(forward_square) is not None
            attacked_by_pawn = bool(board.attackers(not color, forward_square) & enemy_pawns)
            if blocked or attacked_by_pawn:
                score -= BACKWARD_PAWN_PENALTY
        return score
    return _side_difference(board, side_score)


def passed_pawns(board: chess.Board) -> float:
    """Reward passed pawns more as they advance, with extra endgame emphasis."""
    phase = game_phase(board)
    endgame_scale = (
        MAX_GAME_PHASE + PASSED_PAWN_ENDGAME_SCALE * (MAX_GAME_PHASE - phase)
    ) / MAX_GAME_PHASE

    def side_score(color):
        own_pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, not color)
        score = 0.0
        for square in own_pawns:
            relative_rank = chess.square_rank(square) + 1 if color == chess.WHITE else 8 - chess.square_rank(square)
            if not enemy_pawns & _PASSED_PAWN_MASKS[color][square]:
                score += PASSED_PAWN_BONUSES[min(relative_rank, 7)] * endgame_scale
        return score
    return _side_difference(board, side_score)


def protected_pawns(board: chess.Board) -> float:
    """Reward pawns defended by at least one friendly pawn."""
    def side_score(color):
        pawns = board.pieces(chess.PAWN, color)
        return PROTECTED_PAWN_BONUS * sum(
            bool(chess.BB_PAWN_ATTACKS[not color][square] & pawns.mask)
            for square in pawns
        )
    return _side_difference(board, side_score)


def safe_king_corners(board: chess.Board) -> float:
    """Reward kings on the designated safe corner/castled squares."""
    return _side_difference(
        board,
        lambda color: SAFE_KING_BONUS
        if board.king(color) in _SAFE_KING_SQUARES[color] else 0,
    )


def pawn_shields(board: chess.Board) -> float:
    """Count friendly pawns one or two ranks ahead of the king, up to three."""
    def side_score(color):
        king = board.king(color)
        if king is None:
            return 0
        king_file = chess.square_file(king)
        king_rank = chess.square_rank(king)
        direction = 1 if color == chess.WHITE else -1
        pawns = board.pieces(chess.PAWN, color)
        shield = 0
        for file_index in range(max(0, king_file - 1), min(7, king_file + 1) + 1):
            for distance in (1, 2):
                rank = king_rank + direction * distance
                if 0 <= rank < 8 and chess.square(file_index, rank) in pawns:
                    shield += 1
                    break
        return min(shield, 3) * PAWN_SHIELD_BONUS
    return _side_difference(board, side_score)


def open_king_files(board: chess.Board) -> float:
    """Penalize each adjacent or containing file lacking a friendly pawn."""
    def side_score(color):
        king = board.king(color)
        if king is None:
            return 0
        king_file = chess.square_file(king)
        pawns = board.pieces(chess.PAWN, color)
        open_files = sum(
            not pawns & chess.BB_FILES[file_index]
            for file_index in range(max(0, king_file - 1), min(7, king_file + 1) + 1)
        )
        return -OPEN_KING_FILE_PENALTY * open_files
    return _side_difference(board, side_score)


def central_king_penalty(board: chess.Board) -> float:
    """Penalize an uncastled d/e/f-file king that has lost all castling rights."""
    def side_score(color):
        king = board.king(color)
        if king is None or chess.square_file(king) not in (3, 4, 5):
            return 0
        if board.has_castling_rights(color) or king in _SAFE_KING_SQUARES[color]:
            return 0
        return -CENTRAL_KING_PENALTY
    return _side_difference(board, side_score)


def king_safety(board: chess.Board) -> float:
    """Combine king safety terms and taper them out as the game enters an endgame."""
    phase = game_phase(board)
    raw_score = (
        safe_king_corners(board)
        + pawn_shields(board)
        + open_king_files(board)
        + central_king_penalty(board)
    )
    return raw_score * phase / MAX_GAME_PHASE


def piece_protection(board: chess.Board) -> float:
    """Reward defended pieces and modestly penalize attacked, undefended pieces."""
    def side_score(color):
        score = 0
        for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
            for square in board.pieces(piece_type, color):
                defended = bool(board.attackers(color, square))
                attacked = board.is_attacked_by(not color, square)
                if defended:
                    score += PROTECTED_PIECE_BONUS
                elif attacked:
                    score -= PIECE_VALUES[piece_type] // HANGING_PIECE_DIVISOR
        return score
    return _side_difference(board, side_score)


def bishop_pair(board: chess.Board) -> float:
    """Reward each side that retains both bishops."""
    return _side_difference(
        board,
        lambda color: BISHOP_PAIR_BONUS
        if len(board.pieces(chess.BISHOP, color)) >= 2 else 0,
    )


def rook_file_score(board: chess.Board) -> float:
    """Reward rooks on open or semi-open files."""
    def side_score(color):
        own_pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, not color)
        score = 0
        for square in board.pieces(chess.ROOK, color):
            file_mask = chess.BB_FILES[chess.square_file(square)]
            if own_pawns & file_mask:
                continue
            score += (
                ROOK_OPEN_FILE_BONUS
                if not enemy_pawns & file_mask else ROOK_SEMI_OPEN_FILE_BONUS
            )
        return score
    return _side_difference(board, side_score)


def evaluate(board: chess.Board) -> float:
    """Return a White-perspective score for a non-terminal position."""
    return (
        material(board)
        + piece_square_score(board)
        + doubled_pawns(board)
        + isolated_pawns(board)
        + backward_pawns(board)
        + passed_pawns(board)
        + protected_pawns(board)
        + king_safety(board)
        + piece_protection(board)
        + bishop_pair(board)
        + rook_file_score(board)
    )
