"""Turning text into :class:`~pieces.Move` objects.

Two notations are supported:

* **Long algebraic** (what a human types at the prompt): ``e2e4``, ``e7e8q``
  for a promotion, and ``O-O`` / ``O-O-O`` for castling. Parsed by
  :func:`parse_move`.
* **SAN** (Standard Algebraic Notation, what PGN files use): ``e4``, ``Nf3``,
  ``exd5``, ``O-O``, ``e8=Q``, with optional ``+`` / ``#`` / ``!?`` decorations.
  Parsed by :func:`parse_san`, used by the Deep Blue replay script.

Both work the same way: parse the text into constraints, then pick the unique
legal move that satisfies them. Matching against the legal-move list (rather
than re-deriving geometry) means the parser automatically refuses illegal input
and resolves disambiguation for free.
"""

from __future__ import annotations

from typing import Optional

from pieces import Move, file_of, parse_square, rank_of


def parse_move(board, text: str) -> Optional[Move]:
    """Parse one *human* move in long algebraic notation.

    Returns the matching legal :class:`Move`, or ``None`` if the text is not a
    legal move in the current position.
    """
    text = text.strip()
    legal = board.legal_moves()
    lower = text.lower()

    if lower in ("o-o", "0-0"):
        return _find_castle(legal, king_side=True)
    if lower in ("o-o-o", "0-0-0"):
        return _find_castle(legal, king_side=False)

    body = text.replace("=", "")
    if len(body) < 4:
        return None
    try:
        frm = parse_square(body[0:2])
        to = parse_square(body[2:4])
    except ValueError:
        return None

    promotion = None
    if len(body) >= 5:
        promotion = body[4].upper()
        if promotion not in "QRBN":
            return None

    return _select(legal, frm, to, promotion)


def parse_san(board, san: str) -> Optional[Move]:
    """Parse one move in Standard Algebraic Notation (for PGN replay)."""
    s = san.strip().replace("e.p.", "")
    s = s.rstrip("+#!?")  # drop check / mate / annotation glyphs
    legal = board.legal_moves()

    if s in ("O-O", "0-0"):
        return _find_castle(legal, king_side=True)
    if s in ("O-O-O", "0-0-0"):
        return _find_castle(legal, king_side=False)

    promotion = None
    if "=" in s:
        s, promo = s.split("=", 1)
        promotion = promo[0].upper()

    if s and s[0] in "NBRQK":
        piece_letter, rest = s[0], s[1:]
    else:
        piece_letter, rest = "P", s
    rest = rest.replace("x", "")

    # A pawn promotion sometimes appears without '=', e.g. "e8Q".
    if promotion is None and piece_letter == "P" and rest and rest[-1] in "QRBN":
        promotion, rest = rest[-1], rest[:-1]

    if len(rest) < 2:
        return None
    to = parse_square(rest[-2:])

    dis_file = dis_rank = None
    for ch in rest[:-2]:
        if ch in "abcdefgh":
            dis_file = ord(ch) - ord("a")
        elif ch in "12345678":
            dis_rank = int(ch) - 1

    matches = []
    for m in legal:
        p = board.squares[m.from_sq]
        if p is None or p.LETTER != piece_letter or m.to_sq != to:
            continue
        if promotion is None and m.promotion is not None:
            continue
        if promotion is not None and m.promotion != promotion:
            continue
        if dis_file is not None and file_of(m.from_sq) != dis_file:
            continue
        if dis_rank is not None and rank_of(m.from_sq) != dis_rank:
            continue
        matches.append(m)

    return matches[0] if len(matches) == 1 else (matches[0] if matches else None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _find_castle(legal, king_side: bool) -> Optional[Move]:
    target_file = 6 if king_side else 2     # g-file or c-file
    for m in legal:
        if m.is_castle and file_of(m.to_sq) == target_file:
            return m
    return None


def _select(legal, frm: int, to: int, promotion: Optional[str]) -> Optional[Move]:
    candidates = [m for m in legal if m.from_sq == frm and m.to_sq == to]
    if not candidates:
        return None
    if promotion:
        for m in candidates:
            if m.promotion == promotion:
                return m
        return None
    # No promotion piece given: default to a queen if this is a promotion.
    promos = [m for m in candidates if m.promotion]
    if promos:
        for m in promos:
            if m.promotion == "Q":
                return m
        return promos[0]
    return candidates[0]
