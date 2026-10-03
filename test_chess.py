"""Test suite for the chess engine.

Run with::

    python -m unittest -v          # or just: python test_chess.py

The backbone is **perft** (move-path enumeration). If the node counts match the
known reference values, the move generator, the legality filter and make/unmake
are almost certainly correct -- it catches the overwhelming majority of bugs in
a few lines. On top of that we test each rule the brief and the review call out
explicitly: the special moves and their nasty edge cases, every end-of-game
condition, and FEN round-tripping.
"""

import random
import unittest

from board import Board
from game import Game
from notation import parse_move
from pieces import Bishop, King, Queen, WHITE, BLACK
from players import MinimaxPlayer, RandomPlayer


def perft(board: Board, depth: int) -> int:
    """Count the leaf nodes of the legal-move tree to *depth*."""
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves():
        board.make_move(move)
        total += perft(board, depth - 1)
        board.unmake_move()
    return total


def play(moves):
    """Build a game by applying long-algebraic *moves* in order."""
    game = Game()
    for text in moves:
        move = parse_move(game.board, text)
        assert move is not None, f"illegal test move: {text}"
        game.push(move)
    return game


class TestPerft(unittest.TestCase):
    """Move-generation correctness via node counts."""

    def test_startpos(self):
        board = Board.starting_position()
        for depth, expected in {1: 20, 2: 400, 3: 8902, 4: 197281}.items():
            with self.subTest(depth=depth):
                self.assertEqual(perft(board, depth), expected)

    def test_kiwipete(self):
        # The standard position that stresses castling, en passant and promotion.
        fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
        board = Board.from_fen(fen)
        for depth, expected in {1: 48, 2: 2039, 3: 97862}.items():
            with self.subTest(depth=depth):
                self.assertEqual(perft(board, depth), expected)


class TestCheckmate(unittest.TestCase):
    def test_fools_mate(self):
        game = play(["f2f3", "e7e5", "g2g4", "d8h4"])
        self.assertTrue(game.board.is_checkmate())
        self.assertEqual(game.update_result(), "0-1")
        self.assertEqual(game.termination, "checkmate")

    def test_scholars_mate(self):
        game = play(["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"])
        self.assertTrue(game.board.is_checkmate())
        self.assertEqual(game.update_result(), "1-0")
        self.assertEqual(game.termination, "checkmate")


class TestStalemate(unittest.TestCase):
    def test_king_and_queen_stalemate(self):
        # Black king on h8, boxed in but not in check.
        board = Board.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
        self.assertFalse(board.is_in_check(BLACK))
        self.assertEqual(board.legal_moves(), [])
        self.assertTrue(board.is_stalemate())
        self.assertEqual(Game(board).update_result(), "1/2-1/2")


class TestEnPassant(unittest.TestCase):
    def test_basic_capture(self):
        # Black plays d7-d5; White captures e5xd6 e.p.
        board = Board.from_fen("4k3/3p4/8/4P3/8/8/8/4K3 b - - 0 1")
        from pieces import parse_square
        game = Game(board)
        game.push(parse_move(board, "d7d5"))
        self.assertEqual(board.ep_square, parse_square("d6"))
        ep = parse_move(board, "e5d6")
        self.assertIsNotNone(ep)
        self.assertTrue(ep.is_en_passant)
        game.push(ep)
        # The captured black pawn (on d5) is gone; a white pawn sits on d6.
        self.assertIsNone(board.piece_at(parse_square("d5")))
        self.assertEqual(board.piece_at(parse_square("d6")).symbol(), "P")

    def test_discovered_check_is_illegal(self):
        # Famous edge case: the e.p. capture would expose the black king to the
        # white rook along the 4th rank, so it must NOT be legal.
        board = Board.from_fen("8/8/8/8/k2pP2R/8/8/4K3 b - e3 0 1")
        legal = board.legal_moves()
        ep_moves = [m for m in legal if m.is_en_passant]
        self.assertEqual(ep_moves, [], "en passant should be pinned out here")
        # The ordinary push d4-d3 is still legal (the e4 pawn keeps the line shut).
        self.assertIsNotNone(parse_move(board, "d4d3"))


class TestCastling(unittest.TestCase):
    BASE = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"

    def test_both_sides_legal(self):
        board = Board.from_fen(self.BASE)
        self.assertIsNotNone(parse_move(board, "O-O"))
        self.assertIsNotNone(parse_move(board, "O-O-O"))

    def test_cannot_castle_out_of_check(self):
        board = Board.from_fen("4r3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        self.assertTrue(board.is_in_check(WHITE))
        self.assertIsNone(parse_move(board, "O-O"))
        self.assertIsNone(parse_move(board, "O-O-O"))

    def test_cannot_castle_through_check(self):
        # Black rook on f8 attacks f1, the king's transit square king-side.
        board = Board.from_fen("5r2/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        self.assertIsNone(parse_move(board, "O-O"))
        self.assertIsNotNone(parse_move(board, "O-O-O"))

    def test_cannot_castle_into_check(self):
        # Black rook on g8 attacks g1, the king's landing square king-side.
        board = Board.from_fen("6r1/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        self.assertIsNone(parse_move(board, "O-O"))
        self.assertIsNotNone(parse_move(board, "O-O-O"))

    def test_cannot_castle_when_blocked(self):
        # A queen on d1 blocks the queen-side path.
        board = Board.from_fen("r3k2r/8/8/8/8/8/8/R2QK2R w KQ - 0 1")
        self.assertIsNone(parse_move(board, "O-O-O"))
        self.assertIsNotNone(parse_move(board, "O-O"))

    def test_castle_moves_the_rook(self):
        from pieces import parse_square
        board = Board.from_fen(self.BASE)
        board.make_move(parse_move(board, "O-O"))
        self.assertEqual(board.piece_at(parse_square("g1")).symbol(), "K")
        self.assertEqual(board.piece_at(parse_square("f1")).symbol(), "R")
        self.assertIsNone(board.piece_at(parse_square("h1")))


class TestPromotion(unittest.TestCase):
    def test_all_four_promotions_generated(self):
        board = Board.from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        promos = {m.promotion for m in board.legal_moves()
                  if m.from_sq == 48 and m.to_sq == 56}
        self.assertEqual(promos, {"Q", "R", "B", "N"})

    def test_promote_to_queen(self):
        from pieces import parse_square
        board = Board.from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        board.make_move(parse_move(board, "a7a8q"))
        self.assertEqual(board.piece_at(parse_square("a8")).symbol(), "Q")

    def test_underpromotion_to_knight(self):
        from pieces import parse_square
        board = Board.from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        board.make_move(parse_move(board, "a7a8n"))
        self.assertEqual(board.piece_at(parse_square("a8")).symbol(), "N")


class TestThreefold(unittest.TestCase):
    def test_repeating_knight_dance(self):
        cycle = ["g1f3", "g8f6", "f3g1", "f6g8"]
        game = Game()
        # Initial position counts once; each full cycle returns to it.
        for text in cycle:                      # 2nd occurrence
            game.push(parse_move(game.board, text))
        self.assertFalse(game.is_threefold_repetition())
        for text in cycle:                      # 3rd occurrence
            game.push(parse_move(game.board, text))
        self.assertTrue(game.is_threefold_repetition())
        self.assertEqual(game.update_result(), "1/2-1/2")
        self.assertEqual(game.termination, "threefold repetition")


class TestInsufficientMaterial(unittest.TestCase):
    def _insufficient(self, fen):
        return Board.from_fen(fen).is_insufficient_material()

    def test_dead_positions(self):
        self.assertTrue(self._insufficient("4k3/8/8/8/8/8/8/4K3 w - - 0 1"))      # K v K
        self.assertTrue(self._insufficient("4k3/8/8/8/8/8/8/3BK3 w - - 0 1"))     # K+B v K
        self.assertTrue(self._insufficient("4k3/8/8/8/8/8/8/3NK3 w - - 0 1"))     # K+N v K
        # K+B v K+B, bishops on same colour (f1 and c8 are both light).
        self.assertTrue(self._insufficient("2b1k3/8/8/8/8/8/8/5BK1 w - - 0 1"))

    def test_sufficient_material(self):
        # K+B v K+B on opposite colours can (in principle) still be played on.
        self.assertFalse(self._insufficient("5b2/4k3/8/8/8/8/8/5BK1 w - - 0 1"))
        self.assertFalse(self._insufficient("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"))   # queen
        self.assertFalse(self._insufficient("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"))  # pawn


class TestFiftyMoveRule(unittest.TestCase):
    def test_clock_at_hundred(self):
        board = Board.from_fen("4k3/8/8/8/8/8/4P3/4K3 w - - 100 80")
        self.assertTrue(board.is_fifty_move_rule())
        game = Game(board)
        self.assertEqual(game.update_result(), "1/2-1/2")
        self.assertEqual(game.termination, "fifty-move rule")


class TestFenRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        fens = [
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            "8/8/8/8/k2pP2R/8/8/4K3 b - e3 0 1",
            "8/7R/5q1k/3Q2N1/3p4/PP3pPP/5n1K/4r3 b - - 0 37",
        ]
        for fen in fens:
            with self.subTest(fen=fen):
                self.assertEqual(Board.from_fen(fen).to_fen(), fen)


class TestMakeUnmakeInvariant(unittest.TestCase):
    def test_reversible_over_random_games(self):
        """After make+unmake the FEN must be byte-for-byte identical."""
        rng = random.Random(12345)
        for _ in range(3):
            board = Board.starting_position()
            for _ in range(120):
                legal = board.legal_moves()
                if not legal:
                    break
                move = rng.choice(legal)
                before = board.to_fen()
                board.make_move(move)
                board.unmake_move()
                self.assertEqual(board.to_fen(), before)
                board.make_move(move)   # advance the game


class TestEngine(unittest.TestCase):
    def test_minimax_finds_mate_in_one(self):
        # Back-rank mate: Ra8#.
        board = Board.from_fen("6k1/5ppp/8/8/8/8/8/R6K w - - 0 1")
        engine = MinimaxPlayer(depth=2, seed=0)
        move = engine.choose_move(Game(board))
        board.make_move(move)
        self.assertTrue(board.is_checkmate())

    def test_random_player_only_makes_legal_moves(self):
        board = Board.starting_position()
        engine = RandomPlayer(seed=0)
        move = engine.choose_move(Game(board))
        self.assertIn(move, board.legal_moves())


class TestGameFlow(unittest.TestCase):
    def test_random_self_play_terminates(self):
        """A full engine-vs-engine game reaches a well-formed result."""
        def run(seed):
            game = Game()
            white, black = RandomPlayer(seed=seed), RandomPlayer(seed=seed + 100)
            players = {WHITE: white, BLACK: black}
            for _ in range(600):                # generous safety cap
                legal = game.board.legal_moves()
                if game.update_result(legal) is not None:
                    return game
                game.push(players[game.board.side_to_move].choose_move(game))
            return game

        for seed in (1, 7, 42):
            game = run(seed)
            self.assertIn(game.result, {"1-0", "0-1", "1/2-1/2"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
