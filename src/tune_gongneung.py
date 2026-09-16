# -*- coding: utf-8 -*-
"""공릉 일대 '평균적인 판'에 맞는 아이템 개수를 찾는다.

■ 왜 평균인가 (사장님 2026-09-17)
실제 플레이는 공릉동 안의 임의 지점쌍이다. 루트 하나에 맞추면 다른 날 망한다.
sample_gongneung.py 에서 확인된 대로 같은 거리라도 난이도가 30%p 넘게 갈리므로,
**여러 루트에 걸친 중앙값이 50%** 가 되도록 맞추는 것이 옳다.

또한 폭(최소~최대)도 같이 본다. 중앙값만 맞고 폭이 넓으면 "어떤 날은 학살,
어떤 날은 산책"이 된다.

    python src/tune_gongneung.py
"""
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import networkx as nx

import cross_district as cd
import solve_items as si

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

si.MC = 1200                  # 오차 ±2.9%p. 루트 24개 평균이라 실효 오차는 훨씬 작다
DISK = "석계역_공릉역_walk.graphml"
MAX_OFF_M = 1400
WALK_MIN = (25.0, 32.0)
N_ROUTES = 24
SEED = 20260917               # sample_gongneung.py 와 같은 루트 집합

ALLOCS = [
    ([0, 0, 0], [0, 0, 0], "아이템 없음"),
    ([0, 0, 1], [0, 0, 1], "재도전 1:1"),
    ([0, 1, 1], [0, 1, 1], "직진1+재도전1 : 같음"),
    ([0, 0, 1], [0, 0, 0], "재도전 1:0"),
    ([0, 1, 0], [0, 1, 0], "직진 1:1"),
    ([0, 0, 2], [0, 0, 1], "재도전 2:1"),
    ([1, 0, 1], [0, 1, 0], "승리1+재도전1 : 직진1"),
    ([0, 1, 1], [0, 1, 0], "직진1+재도전1 : 직진1"),
    ([1, 0, 0], [0, 0, 0], "무조건승리 1:0"),
    ([0, 1, 1], [0, 0, 1], "직진1+재도전1 : 재도전1"),
]


def main():
    print("공릉 일대 평균에 맞춘 아이템 튜닝 | 루트 %d개 x MC %d판"
          % (N_ROUTES, si.MC))
    Gc, S, pos = cd.district_graph(DISK)
    S = S.subgraph(max(nx.connected_components(S), key=len)).copy()
    xs = [pos[n][0] for n in S]
    ys = [pos[n][1] for n in S]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    core = [n for n in S
            if ((pos[n][0] - cx) ** 2 + (pos[n][1] - cy) ** 2) ** 0.5 <= MAX_OFF_M]

    rng = random.Random(SEED)
    routes = []
    while len(routes) < N_ROUTES:
        a, b = rng.sample(core, 2)
        try:
            t = nx.shortest_path_length(S, a, b, weight="w")
        except nx.NetworkXNoPath:
            continue
        if WALK_MIN[0] <= t <= WALK_MIN[1]:
            routes.append((a, b, t))
    print("  루트 %d개 확보, 도보 %.1f~%.1f분\n"
          % (len(routes), min(r[2] for r in routes), max(r[2] for r in routes)))

    # 목적지별 가치함수는 한 번만 푼다
    print("  가치함수 계산 중...")
    Vs = [si.solve(S, b, p_shadow=2 / 6.0) for _a, b, _t in routes]

    print("\n  구성                        중앙값   평균    최소    최대    폭")
    print("  " + "-" * 68)
    best = None
    for e, se, note in ALLOCS:
        vals = []
        for (a, b, _t), V in zip(routes, Vs):
            _, r90, _ = si.rate(S, pos, V, a, b, e, se, 40.0, n_exp=4, n_sha=2)
            vals.append(r90)
        med = st.median(vals)
        star = " <<<" if 0.45 <= med <= 0.55 else ""
        print("  %-26s %6.1f%% %6.1f%% %6.1f%% %6.1f%% %5.1f%%p%s"
              % (note, 100 * med, 100 * st.mean(vals), 100 * min(vals),
                 100 * max(vals), 100 * (max(vals) - min(vals)), star))
        if best is None or abs(med - 0.5) < abs(best[0] - 0.5):
            best = (med, note, e, se, vals)

    med, note, e, se, vals = best
    print("\n  >> 중앙값이 50%%에 가장 가까운 구성: %s  (%.1f%%)" % (note, 100 * med))
    print("     4:2 = 원정대 %s / 쉐도우 %s" % (si.fmt(e), si.fmt(se)))
    inband = sum(1 for x in vals if 0.40 <= x <= 0.60) / len(vals)
    print("     이 구성에서 루트의 %.0f%%가 40~60%% 구간에 들어온다." % (100 * inband))


if __name__ == "__main__":
    main()
