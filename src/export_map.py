# -*- coding: utf-8 -*-
"""브라우저 게임용으로 공릉 일대 보행망을 JSON 으로 내보낸다.

브라우저판은 서버 없이 HTML 하나로 돌아야 하므로, 그래프를 통째로 실어 보낸다.
병합(tolerance 25 m) 후 노드가 1천 개 안쪽이라 용량이 작고, 가치반복도
자바스크립트에서 1초 안에 끝난다.

좌표는 렌더링 편의를 위해 위경도와 투영좌표(m)를 둘 다 넣는다.
- 위경도: 네이버 지도 링크 등 외부 연동용
- 투영좌표: 화면에 그릴 때 왜곡 없이 쓰기 위함 (위도에 따른 축척 보정 불필요)

    python src/export_map.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

import cross_district as cd
import rsp_map as rm
import solve_items as si

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DISK = "석계역_공릉역_walk.graphml"
OUT = os.path.join(rm.ROOT, "web", "gongneung.json")


def main():
    print("공릉 보행망 -> JSON")
    Gc, S, pos = cd.district_graph(DISK)
    S = S.subgraph(max(nx.connected_components(S), key=len)).copy()
    print("  병합 후 노드 %d / 엣지 %d" % (S.number_of_nodes(),
                                          S.number_of_edges()))

    nodes = sorted(S.nodes())
    idx = {n: i for i, n in enumerate(nodes)}

    # 투영좌표 -> 위경도 (한 번에 변환)
    pts = gpd.GeoDataFrame(
        geometry=[Point(pos[n][0], pos[n][1]) for n in nodes],
        crs=Gc.graph["crs"]).to_crs("EPSG:4326")

    x0 = min(pos[n][0] for n in nodes)
    y0 = min(pos[n][1] for n in nodes)

    out_nodes = []
    for i, n in enumerate(nodes):
        out_nodes.append({
            "x": round(pos[n][0] - x0, 1),        # m, 좌하단 기준
            "y": round(pos[n][1] - y0, 1),
            "lat": round(pts.geometry[i].y, 6),
            "lon": round(pts.geometry[i].x, 6),
        })

    out_edges = []
    for u, v, d in S.edges(data=True):
        out_edges.append([idx[u], idx[v], round(d["w"], 3)])   # 분 단위

    data = {
        "meta": {
            "source": DISK,
            "tolerance_m": si.TOLERANCE,
            "walk_kmh": si.WALK_KMH,
            "sec_per_rps_round": si.SEC_PER_ROUND,
            "note": "RSP 게임용 공릉 일대 보행망. w = 도보 분.",
        },
        "nodes": out_nodes,
        "edges": out_edges,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("  저장 %s  (%.0f KB)" % (OUT, os.path.getsize(OUT) / 1024.0))

    w = max(n["x"] for n in out_nodes)
    h = max(n["y"] for n in out_nodes)
    print("  범위 %.0f x %.0f m" % (w, h))
    degs = dict(S.degree())
    print("  갈림길(3갈래+) %d개, 막다른길 %d개"
          % (sum(1 for d in degs.values() if d >= 3),
             sum(1 for d in degs.values() if d == 1)))


if __name__ == "__main__":
    main()
