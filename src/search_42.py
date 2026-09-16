# -*- coding: utf-8 -*-
"""4:2 에서 가장 균형 잡히고 안정적인 아이템 분배를 찾는다.

사장님이 5:2 로 못 바꾸시는 경우를 위한 답이다. 4:2 는 쉐도우 갈림길 승률이
33.3% 로 높아서 아이템으로 메워야 하는 폭이 크다.

평가 기준 두 가지를 동시에 본다:
  균형  |90분 도착률 - 50%|          작을수록 좋다
  안정  |θ=40 결과 - θ=0 결과|       작을수록 좋다
        (아이템 운용 숙련도에 밸런스가 휘둘리지 않아야 한다)

점수 = 균형오차 + 0.5 x 숙련도편차   (낮을수록 좋음)

    python src/search_42.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import networkx as nx

import solve_items as si

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

si.MC = 2500                      # 조합이 많으므로 판수를 줄인다 (오차 ±2.0%p)

EXP_SET = [
    [0, 0, 1], [0, 0, 2], [0, 0, 3],
    [0, 1, 0], [0, 1, 1], [0, 1, 2], [0, 2, 1],
    [1, 0, 1], [1, 0, 2],
    [1, 1, 1], [1, 1, 2],
    [2, 0, 1], [2, 1, 1],
]
SHA_SET = [
    [0, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
    [0, 1, 1],
]


def main():
    print("4:2 아이템 분배 탐색 | MC %d판 (오차 ±2.0%%p)" % si.MC)
    S, pos, start, goal = si.build()
    V = si.solve(S, goal, p_shadow=2 / 6.0)
    free = nx.shortest_path_length(S, start, goal, weight="w")
    b = si.rate(S, pos, V, start, goal, [0, 0, 0], [0, 0, 0], 40.0,
                n_exp=4, n_sha=2)
    print("  방해 없는 도보 %.1f분 | 기준선 90분 %.1f%%\n" % (free, 100 * b[1]))

    rows = []
    for se in SHA_SET:
        for e in EXP_SET:
            _, a90, _ = si.rate(S, pos, V, start, goal, e, se, 40.0,
                                n_exp=4, n_sha=2)
            c60, c90, _ = si.rate(S, pos, V, start, goal, e, se, 0.0,
                                  n_exp=4, n_sha=2)
            spread = abs(a90 - c90)
            score = abs(a90 - 0.5) + 0.5 * spread
            rows.append((score, e, se, a90, c90, spread, c60))

    rows.sort(key=lambda r: r[0])
    print("  === 좋은 순서 (균형 + 안정) ===")
    print("  순위  원정대  쉐도우 | 90분 θ=40   θ=0  | 편차 | 점수")
    print("  " + "-" * 62)
    for i, (sc, e, se, a90, c90, sp, _c60) in enumerate(rows[:15], 1):
        print("  %3d   %-7s %-6s | %6.1f%% %6.1f%% | %4.1f | %.3f"
              % (i, si.fmt(e), si.fmt(se), 100 * a90, 100 * c90, 100 * sp, sc))

    print("\n  === 쉐도우 구성별 최선 ===")
    print("  쉐도우  | 원정대  | 90분 θ=40   θ=0  | 편차")
    print("  " + "-" * 52)
    for se in SHA_SET:
        cand = [r for r in rows if r[2] == se]
        sc, e, _, a90, c90, sp, _ = cand[0]
        print("  %-7s | %-7s | %6.1f%% %6.1f%% | %4.1f"
              % (si.fmt(se), si.fmt(e), 100 * a90, 100 * c90, 100 * sp))


if __name__ == "__main__":
    main()
