# -*- coding: utf-8 -*-
"""공릉 일대에서 '아무 두 지점'을 잡았을 때 난이도가 어떻게 흩어지는가.

■ 왜 이걸 보는가 (사장님 2026-09-17)
실제 플레이는 역->역이 아니라 **공릉동 안의 임의 지점**끼리다
(예: 서울과기대 미래관 -> 공릉닭한마리). 그러면 "이 루트가 공정한가"가 아니라
**"25~30분 거리로 아무 데나 두 점을 잡으면 난이도가 어떻게 분포하는가"**
가 답해야 할 질문이 된다.

아이템 개수도 특정 루트가 아니라 **분포의 중앙값**에 맞춰야 한다.

■ 방법
가장 해상도 높은 원반 지도(석계-공릉, 437 노드/km2)에서 중심 부근 노드만
후보로 삼아(경계 잘림 회피) 도보 25~32분 쌍을 무작위로 뽑고, 각각에 대해
기준선과 권고안 승률을 잰다.

    python src/sample_gongneung.py
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

si.MC = 1500                  # 루트가 많으므로 판수를 줄인다 (오차 ±2.6%p)
DISK = "석계역_공릉역_walk.graphml"
MAX_OFF_M = 1400              # 원반 중심에서 이 안의 노드만 시종점 후보
WALK_MIN = (25.0, 32.0)       # 사장님 기준 '도보 25~30분' 대역
N_ROUTES = 24
SEED = 20260917

CONFIGS = [
    ([0, 0, 0], [0, 0, 0], "기준선"),
    ([0, 0, 2], [0, 0, 1], "재도전2:1"),
    ([0, 0, 3], [0, 0, 1], "재도전3:1"),
]


def main():
    print("공릉 일대 임의 지점쌍 난이도 분포 | MC %d판/루트 (오차 ±2.6%%p)"
          % si.MC)
    Gc, S, pos = cd.district_graph(DISK)
    big = max(nx.connected_components(S), key=len)
    S = S.subgraph(big).copy()

    xs = [pos[n][0] for n in S]
    ys = [pos[n][1] for n in S]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    core = [n for n in S
            if ((pos[n][0] - cx) ** 2 + (pos[n][1] - cy) ** 2) ** 0.5 <= MAX_OFF_M]
    print("  지도 노드 %d | 중심 %dm 안 후보 노드 %d\n"
          % (S.number_of_nodes(), MAX_OFF_M, len(core)))

    rng = random.Random(SEED)
    routes = []
    tries = 0
    while len(routes) < N_ROUTES and tries < 20000:
        tries += 1
        a, b = rng.sample(core, 2)
        try:
            t = nx.shortest_path_length(S, a, b, weight="w")
        except nx.NetworkXNoPath:
            continue
        if WALK_MIN[0] <= t <= WALK_MIN[1]:
            routes.append((a, b, t))
    print("  %d개 루트 확보 (%d회 시도)\n" % (len(routes), tries))

    print("  #   도보(분) | " + " | ".join("%-9s" % c[2] for c in CONFIGS))
    print("  " + "-" * 52)
    cols = {i: [] for i in range(len(CONFIGS))}
    for i, (a, b, t) in enumerate(routes, 1):
        V = si.solve(S, b, p_shadow=2 / 6.0)
        cells = []
        for j, (e, se, _n) in enumerate(CONFIGS):
            _, r90, _ = si.rate(S, pos, V, a, b, e, se, 40.0, n_exp=4, n_sha=2)
            cols[j].append(r90)
            cells.append("%8.1f%%" % (100 * r90))
        print("  %2d    %5.1f   | %s" % (i, t, " | ".join(cells)))

    print("\n  === 분포 ===")
    print("  구성        최소     중앙값    최대    폭      45~55%% 비율")
    print("  " + "-" * 60)
    for j, (_e, _se, note) in enumerate(CONFIGS):
        v = sorted(cols[j])
        inband = sum(1 for x in v if 0.45 <= x <= 0.55) / len(v)
        print("  %-10s %6.1f%%  %6.1f%%  %6.1f%%  %5.1f%%p   %5.0f%%"
              % (note, 100 * v[0], 100 * st.median(v), 100 * v[-1],
                 100 * (v[-1] - v[0]), 100 * inband))

    print("\n  ※ 중앙값이 50%에 가깝고 폭이 좁아야 '동네 아무 데서나 공정'하다.")
    print("     폭이 크면 아이템이 아니라 출발/도착 지점 선정이 밸런스를 지배한다.")


if __name__ == "__main__":
    main()
