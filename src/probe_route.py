# -*- coding: utf-8 -*-
"""석계역 -> 공릉역 실제 도보 루트를 지도에서 뽑아 현실과 대조한다.

사장님이 알려준 지상 진실(ground truth): 네이버/구글 도보 기준 25~30분.
여기서 나온 값이 그 범위에 들어와야 뒤에 쌓을 계산(갈림길 기댓값)이 의미를 갖는다.

    python src/probe_route.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

import rsp_map as rm

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

START_Q = "석계역, 서울"
GOAL_Q = "공릉역, 서울"
# 네이버/구글 도보 소요시간 (사장님 실측 기준)
GT_MIN = (25, 30)

geocode = rm._resolve("geocode", "geocoder.geocode")
graph_from_point = rm._resolve("graph_from_point")
nearest_nodes = rm._resolve("distance.nearest_nodes", "nearest_nodes")


def main():
    print("osmnx %s\n" % rm.ox.__version__)

    s = geocode(START_Q)
    g = geocode(GOAL_Q)
    print("  %-14s -> %.5f, %.5f" % (START_Q, s[0], s[1]))
    print("  %-14s -> %.5f, %.5f" % (GOAL_Q, g[0], g[1]))

    mid = ((s[0] + g[0]) / 2.0, (s[1] + g[1]) / 2.0)
    # 우회로까지 담으려면 두 역 간 거리보다 넉넉해야 한다.
    path = os.path.join(rm.DATA, "seokgye_gongneung_walk.graphml")
    if os.path.exists(path):
        print("\n[cache] %s" % os.path.basename(path))
        G = rm.load_graphml(path)
    else:
        print("\n[download] 중간점 반경 2.5 km 보행망")
        G = graph_from_point(mid, dist=2500, network_type="walk")
        os.makedirs(rm.DATA, exist_ok=True)
        rm.save_graphml(G, path)
        print("[saved] %.1f MB" % (os.path.getsize(path) / 1e6))

    Gp = rm.project_graph(G)

    # 위경도 -> 그래프와 같은 투영좌표로 옮긴 뒤 가장 가까운 노드에 스냅
    pts = gpd.GeoDataFrame(geometry=[Point(s[1], s[0]), Point(g[1], g[0])],
                           crs="EPSG:4326").to_crs(Gp.graph["crs"])
    n_s = nearest_nodes(Gp, pts.geometry[0].x, pts.geometry[0].y)
    n_g = nearest_nodes(Gp, pts.geometry[1].x, pts.geometry[1].y)

    route = nx.shortest_path(Gp, n_s, n_g, weight="length")
    dist_m = nx.shortest_path_length(Gp, n_s, n_g, weight="length")

    U = nx.MultiGraph(Gp)
    deg = dict(U.degree())
    junctions = [n for n in route if deg.get(n, 0) >= 3]

    print("\n" + "=" * 58)
    print("  석계역 -> 공릉역  최단 도보 경로")
    print("=" * 58)
    print("  그래프          노드 %d / 엣지 %d" % (Gp.number_of_nodes(),
                                                  U.number_of_edges()))
    print("  경로 거리       %.0f m  (%.2f km)" % (dist_m, dist_m / 1000.0))
    print("  경유 노드       %d 개" % len(route))
    print("  그중 갈림길     %d 개   <- 가위바위보 횟수" % len(junctions))
    print("")
    for kmh in (3.6, 4.0, 4.5, 5.0):
        t = dist_m / 1000.0 / kmh * 60.0
        mark = "  <= 실측 %d~%d분과 일치" % GT_MIN if GT_MIN[0] <= t <= GT_MIN[1] else ""
        print("  도보 %.1f km/h -> %5.1f 분%s" % (kmh, t, mark))

    print("\n  ※ 갈림길 = 무방향 차수 3 이상인 노드. 사장님 규칙의 '횡단보도 포함'")
    print("     과는 셈법이 다를 수 있어 별도 대조가 필요하다.")


if __name__ == "__main__":
    main()
