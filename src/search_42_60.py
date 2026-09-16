# -*- coding: utf-8 -*-
"""4:2, **60분** 기준 최적 아이템 분배.

앞선 search_42.py 는 90분(30분 연장권을 항상 쓴다고 보고)을 목표로 했다.
여기서는 사장님 요청대로 **기본 제한시간 1시간**을 목표로 다시 찾는다.
60분 기준 원정대 기준선은 13.2% 로 90분(27.2%)보다 훨씬 낮으므로, 필요한
아이템 양이 크게 늘어난다.

쉐도우에게는 '무조건승리'를 주지 않는다 (사장님 2026-09-17 판단). 원정대에게만
준다. 그래서 SHA_SET 에는 1번 아이템이 들어간 구성이 없다.

점수 = |60분 도착률 - 50%| + 0.5 x |θ=40 - θ=0|   (낮을수록 좋음)

    python src/search_42_60.py
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

si.MC = 2500                       # 오차 ±2.0%p

# 60분은 문턱이 높아 아이템을 더 많이 봐야 한다.
EXP_SET = [
    [0, 0, 2], [0, 0, 3], [0, 0, 4],
    [0, 1, 1], [0, 1, 2], [0, 1, 3],
    [0, 2, 1], [0, 2, 2],
    [1, 0, 2], [1, 0, 3],
    [1, 1, 1], [1, 1, 2], [1, 1, 3],
    [1, 2, 2], [2, 0, 2], [2, 1, 1], [2, 1, 2], [2, 2, 2],
]
# 쉐도우는 무조건승리 없음
SHA_SET = [
    [0, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
    [0, 1, 1],
]


def main():
    print("4:2 / 60분 기준 | MC %d판 (오차 ±2.0%%p) | 쉐도우 무조건승리 없음"
          % si.MC)
    S, pos, start, goal = si.build()
    V = si.solve(S, goal, p_shadow=2 / 6.0)
    free = nx.shortest_path_length(S, start, goal, weight="w")
    b60, b90, _ = si.rate(S, pos, V, start, goal, [0, 0, 0], [0, 0, 0], 40.0,
                          n_exp=4, n_sha=2)
    print("  방해 없는 도보 %.1f분 | 기준선 60분 %.1f%% / 90분 %.1f%%\n"
          % (free, 100 * b60, 100 * b90))

    rows = []
    for se in SHA_SET:
        for e in EXP_SET:
            a60, a90, _ = si.rate(S, pos, V, start, goal, e, se, 40.0,
                                  n_exp=4, n_sha=2)
            c60, c90, _ = si.rate(S, pos, V, start, goal, e, se, 0.0,
                                  n_exp=4, n_sha=2)
            spread = abs(a60 - c60)
            score = abs(a60 - 0.5) + 0.5 * spread
            rows.append((score, e, se, a60, c60, spread, a90, c90))

    rows.sort(key=lambda r: r[0])
    print("  === 60분 기준 좋은 순서 ===")
    print("  순위  원정대  쉐도우 | 60분 θ=40   θ=0  | 편차 | (참고)90분 θ=40")
    print("  " + "-" * 70)
    for i, (sc, e, se, a60, c60, sp, a90, _c90) in enumerate(rows[:15], 1):
        print("  %3d   %-7s %-6s | %6.1f%% %6.1f%% | %4.1f | %10.1f%%"
              % (i, si.fmt(e), si.fmt(se), 100 * a60, 100 * c60,
                 100 * sp, 100 * a90))

    print("\n  === 쉐도우 구성별 최선 (60분) ===")
    print("  쉐도우  | 원정대  | 60분 θ=40   θ=0  | 편차 | 90분 θ=40")
    print("  " + "-" * 62)
    for se in SHA_SET:
        cand = [r for r in rows if r[2] == se]
        sc, e, _, a60, c60, sp, a90, _ = cand[0]
        print("  %-7s | %-7s | %6.1f%% %6.1f%% | %4.1f | %8.1f%%"
              % (si.fmt(se), si.fmt(e), 100 * a60, 100 * c60,
                 100 * sp, 100 * a90))

    print("\n  ※ 90분 열은 30분 연장권을 쓴 경우다. 60분을 50%로 맞추면")
    print("     연장권까지 쓸 때 원정대가 그만큼 더 유리해진다는 뜻이므로,")
    print("     연장권에 비용을 붙이거나 60분 목표를 45% 아래로 잡는 편이 낫다.")


if __name__ == "__main__":
    main()
