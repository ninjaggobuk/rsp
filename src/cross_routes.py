# -*- coding: utf-8 -*-
"""권고안이 석계역->공릉역 한 루트에만 맞는 건 아닌지 교차검증한다.

지금까지의 결론은 전부 루트 하나 위에서 나왔다. 실제 지도는 동네마다 성격이
다르므로(노원구는 복도형, 성북구는 그물형), 같은 권고가 다른 루트에서도
성립하는지 확인해야 한다.

후보 역쌍을 지오코딩해 실제 도보 거리를 재고, 기준 루트와 비슷한 대역
(1.5~2.4 km = 도보 23~36분)에 드는 것만 골라서 같은 구성으로 돌린다.

    python src/cross_routes.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

import rsp_map as rm
import solve_items as si

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

si.MC = 3000

# ★ 인접역은 1.2 km 남짓이라 기준(1.97 km)과 대역이 안 맞는다.
#   2~3 정거장 떨어진 쌍으로 잡아야 25~30분 도보 루트가 된다.
CANDIDATES = [
    ("석계역", "공릉역", "노원(기준)"),
    ("석계역", "하계역", "노원"),
    ("노원역", "공릉역", "노원"),
    ("상계역", "하계역", "노원"),
    ("길음역", "한성대입구역", "성북"),
    ("미아사거리역", "성신여대입구역", "성북"),
    ("월곡역", "보문역", "성북"),
    ("성신여대입구역", "안암역", "성북"),
]
BAND_KM = (1.5, 2.6)
RETRIES = 3

# (원정대, 쉐도우, 인원, 설명)
CONFIGS = [
    ([0, 0, 0], [0, 0, 0], (4, 2), "4:2 아이템 없음"),
    ([0, 0, 2], [0, 0, 1], (4, 2), "4:2 재도전 2:1"),
    ([0, 0, 0], [0, 0, 0], (5, 2), "5:2 아이템 없음"),
    ([0, 0, 1], [0, 0, 1], (5, 2), "5:2 재도전 1:1"),
    ([0, 1, 1], [0, 1, 0], (5, 2), "5:2 원정대 직진1+재도전1 / 쉐도우 직진1"),
]

geocode = rm._resolve("geocode", "geocoder.geocode")
nearest_nodes = rm._resolve("distance.nearest_nodes", "nearest_nodes")
graph_from_point = rm._resolve("graph_from_point")


def slug(a, b):
    return ("%s_%s" % (a, b)).replace(" ", "")


def retry(fn, what):
    """Overpass/Nominatim 은 자주 타임아웃난다. 몇 번 다시 시도한다."""
    last = None
    for i in range(RETRIES):
        try:
            return fn()
        except Exception as e:
            last = e
            print("      [retry %d/%d] %s : %s"
                  % (i + 1, RETRIES, what, type(e).__name__))
            time.sleep(5 * (i + 1))
    raise last


def load_route(a, b):
    """두 역을 담는 보행 그래프를 받아 캐시하고, 병합 그래프와 시종점을 돌려준다."""
    ll_a = retry(lambda: geocode(a + ", 서울"), "geocode " + a)
    ll_b = retry(lambda: geocode(b + ", 서울"), "geocode " + b)
    mid = ((ll_a[0] + ll_b[0]) / 2.0, (ll_a[1] + ll_b[1]) / 2.0)

    path = os.path.join(rm.DATA, slug(a, b) + "_walk.graphml")
    if os.path.exists(path):
        G = rm.load_graphml(path)
    else:
        G = retry(lambda: graph_from_point(mid, dist=2500, network_type="walk"),
                  "download %s-%s" % (a, b))
        os.makedirs(rm.DATA, exist_ok=True)
        rm.save_graphml(G, path)

    Gp = rm.project_graph(G)
    Gc = si.consolidate(Gp, tolerance=si.TOLERANCE, rebuild_graph=True,
                        dead_ends=True)
    S = nx.Graph()
    for u, v, d in nx.MultiGraph(Gc).edges(data=True):
        if u == v:
            continue
        w = d.get("length", 0.0) / 1000.0 / si.WALK_KMH * 60.0
        if not S.has_edge(u, v) or w < S[u][v]["w"]:
            S.add_edge(u, v, w=w)
    pos = {n: (d["x"], d["y"]) for n, d in Gc.nodes(data=True)}

    pts = gpd.GeoDataFrame(
        geometry=[Point(ll_a[1], ll_a[0]), Point(ll_b[1], ll_b[0])],
        crs="EPSG:4326").to_crs(Gc.graph["crs"])
    s = nearest_nodes(Gc, pts.geometry[0].x, pts.geometry[0].y)
    g = nearest_nodes(Gc, pts.geometry[1].x, pts.geometry[1].y)
    S = S.subgraph(nx.node_connected_component(S, g)).copy()
    if s not in S:
        return None
    return S, pos, s, g


def main():
    print("루트 교차검증 | tol %dm | MC %d판\n" % (si.TOLERANCE, si.MC))

    routes = []
    for a, b, area in CANDIDATES:
        try:
            r = load_route(a, b)
        except Exception as e:
            print("  [skip] %s -> %s : %s" % (a, b, type(e).__name__))
            continue
        if r is None:
            print("  [skip] %s -> %s : 연결 안 됨" % (a, b))
            continue
        S, pos, s, g = r
        try:
            free = nx.shortest_path_length(S, s, g, weight="w")
        except nx.NetworkXNoPath:
            print("  [skip] %s -> %s : 경로 없음" % (a, b))
            continue
        km = free * si.WALK_KMH / 60.0
        ok = BAND_KM[0] <= km <= BAND_KM[1]
        print("  %-10s -> %-12s %-8s %5.2f km / %4.1f분  %s"
              % (a, b, area, km, free, "채택" if ok else "대역 밖"))
        if ok:
            routes.append((a, b, area, S, pos, s, g, free))

    if not routes:
        print("\n대역에 드는 루트가 없다.")
        return

    print("\n  채택 루트 %d개로 구성별 90분 도착률을 비교한다." % len(routes))
    for e, se, (n_e, n_s), note in CONFIGS:
        print("\n  === %s ===" % note)
        print("  루트                        | θ=40    θ=0   | 편차")
        print("  " + "-" * 56)
        vals = []
        for a, b, area, S, pos, s, g, free in routes:
            V = si.solve(S, g, p_shadow=n_s / float(n_e + n_s))
            _, a90, _ = si.rate(S, pos, V, s, g, e, se, 40.0,
                                n_exp=n_e, n_sha=n_s)
            _, c90, _ = si.rate(S, pos, V, s, g, e, se, 0.0,
                                n_exp=n_e, n_sha=n_s)
            vals.append(a90)
            print("  %-10s -> %-12s | %6.1f%% %6.1f%% | %4.1f"
                  % (a, b, 100 * a90, 100 * c90, 100 * abs(a90 - c90)))
        print("  루트 간 범위 %.1f%% ~ %.1f%%  (폭 %.1f%%p)"
              % (100 * min(vals), 100 * max(vals),
                 100 * (max(vals) - min(vals))))


if __name__ == "__main__":
    main()
