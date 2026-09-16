# -*- coding: utf-8 -*-
"""인원 구성별 갈림길 승률 — 이론값과 시뮬레이션 대조.

이론: 전원이 균등 랜덤으로 독립하여 내면, 판정 규칙이 사람을 구별하지 않으므로
과정 전체가 플레이어에 대해 교환가능(exchangeable)하다. 따라서 최후 1인은
모든 참가자에게 균등하고,

        P(팀이 갈림길을 가져감) = 그 팀 인원 / 전체 인원

이 된다. 이 스크립트는 그 값을 시뮬레이션으로 확인하고, 동시에 갈림길 1회에
드는 **라운드 수**(= 실제 경과 시간)를 잰다. 라운드 수는 인원이 늘수록 커지고,
그건 시계를 먹으므로 쉐도우에게 유리하게 작용한다.

    python src/probe_rps_balance.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rps

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TRIALS = 200000
# (원정대, 쉐도우)
SETUPS = [(2, 1), (4, 2), (6, 3), (3, 1), (3, 2), (4, 1), (5, 2), (6, 2), (1, 1)]


def run(n_exp, n_sha, trials=TRIALS, seed=12345):
    rng = random.Random(seed)
    n = n_exp + n_sha
    sha_wins = 0
    total_rounds = 0
    max_rounds = 0
    for _ in range(trials):
        w, r = rps.play_junction(n, rng)
        if w >= n_exp:                      # 인덱스 뒤쪽이 쉐도우
            sha_wins += 1
        total_rounds += r
        max_rounds = max(max_rounds, r)
    return {
        "exp": n_exp, "sha": n_sha, "n": n,
        "sim": sha_wins / trials,
        "theory": n_sha / n,
        "mean_rounds": total_rounds / trials,
        "max_rounds": max_rounds,
    }


def main():
    print("갈림길 1회 — 쉐도우(소수팀) 승률\n")
    print("  구성      전체   이론      시뮬     오차     평균 라운드  최대")
    print("  " + "-" * 62)
    for e, s in SETUPS:
        r = run(e, s)
        print("  %d : %-3d  %3d   %6.2f%%  %6.2f%%  %+5.2f%%p  %8.2f  %5d"
              % (r["exp"], r["sha"], r["n"], 100 * r["theory"], 100 * r["sim"],
                 100 * (r["sim"] - r["theory"]), r["mean_rounds"], r["max_rounds"]))

    print("\n  ※ %d회 시뮬. 이론 = 팀인원/전체인원 (교환가능성)." % TRIALS)


if __name__ == "__main__":
    main()
