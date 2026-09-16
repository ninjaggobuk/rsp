# -*- coding: utf-8 -*-
"""갈림길 하나를 지는 비용, 그리고 실제 승률 — 석계역 -> 공릉역 실지도.

■ 모델
일행은 한 덩어리로 움직인다. 갈림길마다 전원이 탈락식 가위바위보를 하고, 최후
1인의 팀이 방향을 정한다(4:2 -> 쉐도우 1/3). 원정대는 남은 시간을 최소화,
쉐도우는 최대화 — 확률적 2인 게임이다.

상태 = (직전 노드, 현재 노드). 왔던 길로 되돌아가는 선택지는 없다
(사장님 사거리 예시에 U턴이 없다: 직진·우측 횡단보도·좌측 보도 = 3갈래).

  V(목적지) = 0
  갈래 2개+ : V = T_rps + (2/3)·min_t[w+V] + (1/3)·max_t[w+V]
  갈래 1개  : V =         w + V              (선택 없음 = 가위바위보 없음)

■ ★ 교차로 병합이 결정적이다
OSM 은 사거리 하나를 횡단보도·보도 노드 여러 개로 쪼개 놓는다. 병합 없이 풀면
1.8 km 구간에 갈림길이 26개로 잡혀 원정대가 절대 못 이기는 결과가 나온다
(2026-09-17 최초 풀이에서 166분이 나왔다). consolidate_intersections 로
tolerance m 안의 노드를 하나로 합쳐야 현실과 맞는다.
어느 tolerance 가 맞는지는 **실제로 가위바위보를 몇 번 했는지**로 정해야 한다.

    python src/solve_game.py
"""
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

import rps
import rsp_map as rm

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WALK_KMH = 4.0            # probe_route.py 에서 실측 25~30분과 맞은 속도
N_EXP, N_SHA = 4, 2
SEC_PER_ROUND = 6.0       # 가위바위보 1라운드 실소요. ★추정치 — 실측 필요
TOLERANCES = (15, 20, 25)
MC_TRIALS = 4000
TIME_CAP = 300.0          # 분. 넘으면 실패로 센다
TOL_VI, MAX_SWEEP = 1e-7, 20000

consolidate = rm._resolve("simplification.consolidate_intersections",
                          "consolidate_intersections")
geocode = rm._resolve("geocode", "geocoder.geocode")
nearest_nodes = rm._resolve("distance.nearest_nodes", "nearest_nodes")

P_SHADOW = N_SHA / float(N_EXP + N_SHA)


def simple_walk_graph(Gp):
    """MultiGraph -> 평행 엣지를 최단으로 접은 단순 무방향 그래프(가중치=분)."""
    S = nx.Graph()
    for u, v, d in nx.MultiGraph(Gp).edges(data=True):
        if u == v:
            continue
        w = d.get("length", 0.0) / 1000.0 / WALK_KMH * 60.0
        if not S.has_edge(u, v) or w < S[u][v]["w"]:
            S.add_edge(u, v, w=w)
    return S


def options(S, prev, cur):
    opts = [w for w in S[cur] if w != prev]
    return opts if opts else ([prev] if prev is not None else [])


def solve(S, goal, t_rps):
    states = []
    for u, v in S.edges():
        states.append((u, v))
        states.append((v, u))
    V = {s: 0.0 for s in states}
    for sweep in range(MAX_SWEEP):
        delta = 0.0
        for (prev, cur) in states:
            if cur == goal:
                continue
            opts = options(S, prev, cur)
            vals = [S[cur][w]["w"] + V[(cur, w)] for w in opts]
            if len(opts) >= 2:
                new = t_rps + (1.0 - P_SHADOW) * min(vals) + P_SHADOW * max(vals)
            else:
                new = vals[0]
            delta = max(delta, abs(new - V[(prev, cur)]))
            V[(prev, cur)] = new
        if delta < TOL_VI:
            return V, sweep + 1, True
    return V, MAX_SWEEP, False


def play_once(S, V, start, goal, rng):
    """가위바위보를 실제로 굴려 한 판을 끝까지 시뮬레이션한다.

    반환: (도착시간 분, 갈림길 수, 쉐도우가 이긴 횟수, 도착 여부)
    """
    prev, cur = None, start
    t = 0.0
    n_j = n_sha = 0
    while cur != goal and t < TIME_CAP:
        opts = options(S, prev, cur)
        if not opts:
            break
        if len(opts) == 1:
            nxt = opts[0]
        else:
            n_j += 1
            w_idx, rounds = rps.play_junction(N_EXP + N_SHA, rng)
            t += rounds * SEC_PER_ROUND / 60.0
            vals = [(S[cur][w]["w"] + V[(cur, w)], w) for w in opts]
            if w_idx >= N_EXP:                    # 쉐도우 승 -> 최악 선택
                n_sha += 1
                nxt = max(vals)[1]
            else:
                nxt = min(vals)[1]
        t += S[cur][nxt]["w"]
        prev, cur = cur, nxt
    return t, n_j, n_sha, (cur == goal and t <= TIME_CAP)


def analyse(Gp_raw, tol, start_ll, goal_ll, t_rps):
    Gc = consolidate(Gp_raw, tolerance=tol, rebuild_graph=True, dead_ends=True)
    S_all = simple_walk_graph(Gc)

    pts = gpd.GeoDataFrame(
        geometry=[Point(start_ll[1], start_ll[0]), Point(goal_ll[1], goal_ll[0])],
        crs="EPSG:4326").to_crs(Gc.graph["crs"])
    start = nearest_nodes(Gc, pts.geometry[0].x, pts.geometry[0].y)
    goal = nearest_nodes(Gc, pts.geometry[1].x, pts.geometry[1].y)

    S = S_all.subgraph(nx.node_connected_component(S_all, goal)).copy()
    if start not in S:
        return None

    route = nx.shortest_path(S, start, goal, weight="w")
    free_min = nx.shortest_path_length(S, start, goal, weight="w")
    free_j = sum(1 for n in route[:-1] if S.degree(n) >= 3)

    V, sweeps, ok = solve(S, goal, t_rps)

    rng = random.Random(4242)
    times, njs, nshas, arrived = [], [], [], 0
    for _ in range(MC_TRIALS):
        t, nj, ns, ar = play_once(S, V, start, goal, rng)
        times.append(t); njs.append(nj); nshas.append(ns)
        arrived += 1 if ar else 0

    within60 = sum(1 for t in times if t <= 60) / len(times)
    within90 = sum(1 for t in times if t <= 90) / len(times)

    deltas = []
    for (prev, cur) in V:
        if cur == goal:
            continue
        opts = options(S, prev, cur)
        if len(opts) < 2:
            continue
        vals = [S[cur][w]["w"] + V[(cur, w)] for w in opts]
        deltas.append(max(vals) - min(vals))

    return dict(tol=tol, nodes=S.number_of_nodes(), edges=S.number_of_edges(),
                free_min=free_min, free_j=free_j, sweeps=sweeps, converged=ok,
                med=st.median(times), mean=st.mean(times),
                w60=within60, w90=within90, arrived=arrived / MC_TRIALS,
                mean_j=st.mean(njs), mean_sha=st.mean(nshas),
                d_mean=st.mean(deltas), d_med=st.median(deltas),
                d_p90=sorted(deltas)[int(0.9 * len(deltas))], d_max=max(deltas))


def main():
    t_rps_nominal = 6.23 * SEC_PER_ROUND / 60.0
    print("보행 %.1f km/h | %d:%d -> 쉐도우 %.1f%% | 라운드당 %.0f초 "
          "(갈림길 평균 %.2f분)" % (WALK_KMH, N_EXP, N_SHA, 100 * P_SHADOW,
                                    SEC_PER_ROUND, t_rps_nominal))

    G = rm.load_graphml(os.path.join(rm.DATA, "seokgye_gongneung_walk.graphml"))
    Gp = rm.project_graph(G)
    s_ll, g_ll = geocode("석계역, 서울"), geocode("공릉역, 서울")

    out = []
    for tol in TOLERANCES:
        r = analyse(Gp, tol, s_ll, g_ll, t_rps_nominal)
        if r:
            out.append(r)
            print("  [tol=%dm] 노드 %d, 수렴 %s (%d sweep)"
                  % (tol, r["nodes"], r["converged"], r["sweeps"]))

    print("\n" + "=" * 74)
    print("  tol  경로상   방해없는   실제 갈림길  쉐도우   도착시간(분)   60분내  90분내")
    print("   m   갈림길   도보(분)     평균 수    승리수   중앙  평균    도착률  도착률")
    print("  " + "-" * 72)
    for r in out:
        print("  %3d    %3d     %5.1f       %6.1f    %5.1f   %5.1f %5.1f   %5.1f%%  %5.1f%%"
              % (r["tol"], r["free_j"], r["free_min"], r["mean_j"], r["mean_sha"],
                 r["med"], r["mean"], 100 * r["w60"], 100 * r["w90"]))

    print("\n  갈림길 하나를 지는 비용 Δ (분) — 되돌아오며 다시 이겨야 하는 것까지 포함")
    print("  " + "-" * 56)
    print("  tol     평균    중앙값   90분위    최대")
    for r in out:
        print("  %3d   %6.2f  %6.2f  %6.2f  %6.2f"
              % (r["tol"], r["d_mean"], r["d_med"], r["d_p90"], r["d_max"]))

    print("\n  ※ tolerance 는 '사거리 하나를 노드 하나로 합치는 반경'이다.")
    print("     실제로 한 판에 가위바위보를 몇 번 하셨는지와 '실제 갈림길 평균 수'를")
    print("     맞춰보면 어느 tol 이 현실인지 정해진다.")


if __name__ == "__main__":
    main()
