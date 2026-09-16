# -*- coding: utf-8 -*-
"""쉬운 루트와 어려운 루트를 가르는 지형 특징을 찾는다.

■ 왜
tune_gongneung.py 에서 확인된 대로 아이템은 중앙값만 옮기고 **폭(루트 간 30%p)은
못 줄인다**. 분산을 줄이는 유일한 레버는 출발/도착 지점 선정이다. 그러려면
"어떤 지점쌍이 불공정한가"를 사장님이 **지도만 보고** 판단할 수 있어야 한다.

■ 그래서 후보 지표는 전부 '사람이 확인 가능한 것'으로 골랐다
  walk    도보 시간            네이버 지도로 바로 확인
  njunc   경로상 갈림길 수      지도에서 셀 수 있음
  direct  직선거리/도보거리      돌아가는 길인지 (1.0 = 곧게 뻗음)
  loop    경로 주변 고리 수/km   되돌아올 수 있는 순환로가 있는가
  dead    경로 주변 막다른길 비율
  deg     갈림길 평균 갈래 수

목표변수는 권고 구성(재도전 1:1)에서의 90분 도착률이다.

    python src/route_features.py
"""
import math
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

si.MC = 1200
DISK = "석계역_공릉역_walk.graphml"
MAX_OFF_M = 1400
WALK_MIN = (25.0, 32.0)
N_ROUTES = 60
SEED = 424242
NEAR_M = 300.0                       # '경로 주변' 반경
EXP, SHA = [0, 0, 1], [0, 0, 1]      # 권고 구성: 재도전 1:1


def near_nodes(S, pos, path, radius=NEAR_M):
    px = [pos[n][0] for n in path]
    py = [pos[n][1] for n in path]
    out = []
    r2 = radius * radius
    for n in S:
        x, y = pos[n]
        for i in range(len(px)):
            dx = x - px[i]
            dy = y - py[i]
            if dx * dx + dy * dy <= r2:
                out.append(n)
                break
    return out


def features(S, pos, a, b):
    path = nx.shortest_path(S, a, b, weight="w")
    walk = nx.shortest_path_length(S, a, b, weight="w")
    dist_m = walk / 60.0 * si.WALK_KMH * 1000.0

    straight = math.hypot(pos[a][0] - pos[b][0], pos[a][1] - pos[b][1])
    direct = straight / dist_m if dist_m else 0.0

    juncs = [n for n in path[:-1] if S.degree(n) >= 3]
    deg = st.mean([S.degree(n) for n in juncs]) if juncs else 0.0

    nb = near_nodes(S, pos, path)
    H = S.subgraph(nb)
    comps = nx.number_connected_components(H)
    cyclo = H.number_of_edges() - H.number_of_nodes() + comps      # 고리 수
    dead = sum(1 for n in H if H.degree(n) == 1) / max(H.number_of_nodes(), 1)

    return {
        "walk": walk,
        "njunc": len(juncs),
        "direct": direct,
        "loop": cyclo / (dist_m / 1000.0),        # km 당 고리 수
        "dead": dead,
        "deg": deg,
    }


def corr(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    print("루트 지형 특징 vs 난이도 | 루트 %d개 | 구성 재도전 1:1 | MC %d판"
          % (N_ROUTES, si.MC))
    Gc, S, pos = cd.district_graph(DISK)
    S = S.subgraph(max(nx.connected_components(S), key=len)).copy()
    xs = [pos[n][0] for n in S]
    ys = [pos[n][1] for n in S]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    core = [n for n in S
            if math.hypot(pos[n][0] - cx, pos[n][1] - cy) <= MAX_OFF_M]

    rng = random.Random(SEED)
    routes = []
    while len(routes) < N_ROUTES:
        a, b = rng.sample(core, 2)
        try:
            t = nx.shortest_path_length(S, a, b, weight="w")
        except nx.NetworkXNoPath:
            continue
        if WALK_MIN[0] <= t <= WALK_MIN[1]:
            routes.append((a, b))
    print("  루트 %d개 확보\n" % len(routes))

    rows = []
    for i, (a, b) in enumerate(routes, 1):
        f = features(S, pos, a, b)
        V = si.solve(S, b, p_shadow=2 / 6.0)
        _, r90, _ = si.rate(S, pos, V, a, b, EXP, SHA, 40.0, n_exp=4, n_sha=2)
        f["win"] = r90
        rows.append(f)
        if i % 10 == 0:
            print("  ... %d/%d" % (i, len(routes)))

    keys = ["walk", "njunc", "direct", "loop", "dead", "deg"]
    wins = [r["win"] for r in rows]
    print("\n  === 원정대 승률과의 상관계수 ===")
    print("  지표      상관     해석")
    print("  " + "-" * 56)
    label = {
        "walk": "도보 시간", "njunc": "갈림길 수", "direct": "직진성",
        "loop": "주변 고리/km", "dead": "막다른길 비율", "deg": "갈래 평균",
    }
    cs = []
    for k in keys:
        c = corr([r[k] for r in rows], wins)
        cs.append((abs(c), c, k))
        sign = "높을수록 원정대 유리" if c > 0 else "높을수록 원정대 불리"
        print("  %-12s %+.2f    %s" % (label[k], c, sign))

    cs.sort(reverse=True)
    print("\n  가장 강한 예측변수: %s (|r| = %.2f)" % (label[cs[0][2]], cs[0][0]))

    # 상위/하위 사분위 비교 — 실전 규칙으로 쓸 수 있게
    srt = sorted(rows, key=lambda r: r["win"])
    q = max(len(srt) // 4, 1)
    hard, easy = srt[:q], srt[-q:]
    print("\n  === 어려운 루트 %d개 vs 쉬운 루트 %d개 평균 ===" % (q, q))
    print("  지표          어려움    쉬움    차이")
    print("  " + "-" * 48)
    print("  승률         %6.1f%%  %6.1f%%"
          % (100 * st.mean([r["win"] for r in hard]),
             100 * st.mean([r["win"] for r in easy])))
    for k in keys:
        h, e = st.mean([r[k] for r in hard]), st.mean([r[k] for r in easy])
        print("  %-12s %7.2f %7.2f  %+7.2f" % (label[k], h, e, e - h))


if __name__ == "__main__":
    main()
