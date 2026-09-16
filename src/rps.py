# -*- coding: utf-8 -*-
"""다인 가위바위보 판정 — 갈림길 1회분.

규칙(한국 통상):
  전원이 동시에 낸다.
    - 나온 기호가 3종류  -> 무승부, 다시
    - 나온 기호가 1종류  -> 무승부, 다시
    - 나온 기호가 2종류  -> 이기는 기호를 낸 사람만 생존, 나머지 탈락
  1명 남을 때까지 반복. 그 1명의 팀이 그 갈림길을 가져간다.

기호는 0=바위 1=보 2=가위.
"""
import random

ROCK, PAPER, SCISSORS = 0, 1, 2
NAMES = {ROCK: "바위", PAPER: "보", SCISSORS: "가위"}

# beats[a] = a 가 이기는 기호
_BEATS = {ROCK: SCISSORS, PAPER: ROCK, SCISSORS: PAPER}


def winner_symbol(symbols):
    """정확히 2종류일 때 이기는 기호. 그 외에는 None(무승부)."""
    s = set(symbols)
    if len(s) != 2:
        return None
    a, b = tuple(s)
    return a if _BEATS[a] == b else b


def play_junction(n_players, rng, throw=None, max_rounds=10000):
    """n_players 명이 1명 남을 때까지 겨룬다.

    throw(player_index, alive_tuple, round_no) -> 기호. 기본은 균등 랜덤.
    반환: (승자 인덱스, 소요 라운드 수)
    """
    if throw is None:
        def throw(_p, _alive, _r):
            return rng.randrange(3)

    alive = tuple(range(n_players))
    rounds = 0
    while len(alive) > 1:
        rounds += 1
        if rounds > max_rounds:
            raise RuntimeError("가위바위보가 %d 라운드에도 안 끝났다" % max_rounds)
        throws = [throw(p, alive, rounds) for p in alive]
        w = winner_symbol(throws)
        if w is None:
            continue                       # 무승부 — 같은 인원으로 다시
        alive = tuple(p for p, t in zip(alive, throws) if t == w)
    return alive[0], rounds
