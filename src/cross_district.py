# -*- coding: utf-8 -*-
"""루트 교차검증 — 이미 받아둔 노원구/성북구 전체 지도에서 역쌍을 뽑아 쓴다.

왜 이 방식인가: 루트마다 반경 2.5 km 를 새로 받으려 했더니 Overpass 가 전부
ConnectTimeout 으로 막았다. 그런데 맨 처음 받아둔 구 전체 보행망이 캐시에
있으므로 거기서 역쌍을 잘라 쓰면 네트워크가 아예 필요 없다.
부수 효과로 더 정확하기도 하다 — 구 전체라 우회로가 경계에서 잘리지 않고,
**복도형 노원 vs 그물형 성북**(갈림길 밀도 140 vs 252 /km2) 대비가 그대로 산다.

⚠ 구 경계에 걸친 역(석계역은 노원/성북 경계)은 한쪽 구 지도에서 우회로가
   잘릴 수 있다. 결과 해석 시 감안한다.

역 좌표는 한 번 지오코딩해 data/stations.json 에 캐시한다.

    python src/cross_district.py
"""
import itertools
import json
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

DISTRICTS = {
    "노원구": ("노원구_서울특별시_대한민국_walk.graphml",
             ["석계역", "광운대역", "월계역", "공릉역", "태릉입구역",
              "화랑대역", "하계역", "중계역", "노원역", "상계역", "마들역"]),
    "성북구": ("성북구_서울특별시_대한민국_walk.graphml",
             ["길음역", "미아사거리역", "성신여대입구역", "한성대입구역",
              "보문역", "안암역", "월곡역", "상월곡역", "돌곶이역"]),
}
BAND_KM = (1.7, 2.4)       # 기준 루트 1.97 km 주변
MAX_SNAP_M = 400           # 역이 이 거리 안의 노드에 붙어야 그 구에 있다고 본다
PER_DISTRICT = 3           # 구당 검증할 루트 수

CONFIGS = [
    ([0, 0, 0], [0, 0, 0], (4, 2), "4:2 아이템 없음 (기준선)"),
    ([0, 0, 2], [0, 0, 1], (4, 2), "4:2 재도전 2:1  <-- 권고안"),
    ([0, 0, 0], [0, 0, 0], (5, 2), "5:2 아이템 없음"),
    ([0, 0, 1], [0, 0, 1], (5, 2), "5:2 재도전 1:1  <-- 권고안"),
]

geocode = rm._resolve("geocode", "geocoder.geocode")
nearest_nodes = rm._resolve("distance.nearest_nodes", "nearest_nodes")
STATIONS_JSON = os.path.join(rm.DATA, "stations.json")


def station_coords(names):
    """역 -> (lat, lon). 한 번 받으면 파일에 캐시한다."""
    cache = {}
    if os.path.exists(STATIONS_JSON):
        with open(STATIONS_JSON, encoding="utf-8") as f:
            cache = json.load(f)
    missing = [n for n in names if n not in cache]
    for n in missing:
        for attempt in range(3):
            try:
                lat, lon = geocode(n + ", 서울")
                cache[n] = [lat, lon]
                print("    [geocode] %-14s %.5f, %.5f" % (n, lat, lon))
                break
            except Exception as e:
                print("    [retry %d] %s : %s" % (attempt + 1, n, type(e).__name__))
                time.sleep(3)
        time.sleep(1)
    if missing:
        with open(STATIONS_JSON, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    return cache


def district_graph(fname):
    G = rm.load_graphml(os.path.join(rm.DATA, fname))
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
    si.POS = pos          # options() 의 방향 묶기에 쓰인다
    return Gc, S, pos


def snap(Gc, lat, lon):
    """역 좌표를 그래프 노드에 붙이고, 붙은 거리(m)도 돌려준다."""
    pt = gpd.GeoDataFrame(geometry=[Point(lon, lat)],
                          crs="EPSG:4326").to_crs(Gc.graph["crs"]).geometry[0]
    n = nearest_nodes(Gc, pt.x, pt.y)
    dx = Gc.nodes[n]["x"] - pt.x
    dy = Gc.nodes[n]["y"] - pt.y
    return n, (dx * dx + dy * dy) ** 0.5


def main():
    print("구 전체 지도 기반 교차검증 | tol %dm | MC %d판\n"
          % (si.TOLERANCE, si.MC))

    all_names = sorted({n for _, names in DISTRICTS.values() for n in names})
    coords = station_coords(all_names)

    picked = []
    for dname, (fname, names) in DISTRICTS.items():
        print("\n  --- %s ---" % dname)
        Gc, S, pos = district_graph(fname)
        print("  병합 후 노드 %d / 엣지 %d" % (S.number_of_nodes(),
                                             S.number_of_edges()))
        inside = {}
        for n in names:
            if n not in coords:
                continue
            node, dist = snap(Gc, *coords[n])
            if dist <= MAX_SNAP_M and node in S:
                inside[n] = node
        print("  구 안에서 찾은 역 %d개: %s"
              % (len(inside), ", ".join(sorted(inside))))

        cands = []
        for a, b in itertools.combinations(sorted(inside), 2):
            na, nb = inside[a], inside[b]
            if na == nb:
                continue
            try:
                t = nx.shortest_path_length(S, na, nb, weight="w")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            km = t * si.WALK_KMH / 60.0
            if BAND_KM[0] <= km <= BAND_KM[1]:
                cands.append((abs(km - 1.97), a, b, na, nb, km, t))
        cands.sort()
        for _, a, b, na, nb, km, t in cands[:PER_DISTRICT]:
            print("  채택  %-14s -> %-14s %5.2f km / %4.1f분" % (a, b, km, t))
            picked.append((dname, a, b, S, pos, na, nb))

    if not picked:
        print("\n대역에 드는 루트가 없다.")
        return

    print("\n\n검증 루트 %d개\n" % len(picked))
    for e, se, (n_e, n_s), note in CONFIGS:
        print("  === %s ===" % note)
        print("  구      루트                            | θ=40    θ=0   | 편차")
        print("  " + "-" * 66)
        vals = []
        for dname, a, b, S, pos, na, nb in picked:
            V = si.solve(S, nb, p_shadow=n_s / float(n_e + n_s))
            _, a90, _ = si.rate(S, pos, V, na, nb, e, se, 40.0,
                                n_exp=n_e, n_sha=n_s)
            _, c90, _ = si.rate(S, pos, V, na, nb, e, se, 0.0,
                                n_exp=n_e, n_sha=n_s)
            vals.append(a90)
            print("  %-6s  %-12s -> %-14s | %6.1f%% %6.1f%% | %4.1f"
                  % (dname, a, b, 100 * a90, 100 * c90, 100 * abs(a90 - c90)))
        print("  >> 루트 간 %.1f%% ~ %.1f%%   폭 %.1f%%p\n"
              % (100 * min(vals), 100 * max(vals),
                 100 * (max(vals) - min(vals))))


if __name__ == "__main__":
    main()
