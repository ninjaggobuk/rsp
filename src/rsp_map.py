# -*- coding: utf-8 -*-
"""OSM 보행 네트워크 로더 — RSP(가위바위보) 실세계 보드게임용.

플레이어가 실제로 걸어다니는 게임이므로 '판'은 동네의 보행 네트워크다.
노드 = 교차로, 엣지 = 걸어갈 수 있는 구간(길이 m 를 실제로 들고 있음).

한 번 받아서 GraphML 로 캐시하고, 그 동네가 판으로 쓸 만한지 판단하는 데
필요한 수치를 뽑는다 — 크기, 가로질러 걷는 시간, 실제 갈림길이 몇 개인지.

OSMnx 는 2.0 에서 함수 대부분을 서브모듈로 옮겼다. `_resolve` 가 신/구 배치를
모두 받아주므로 conda-forge 가 어느 버전을 깔았든 그대로 돈다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path      # osmnx/matplotlib 보다 먼저
ensure_conda_dll_path()

import networkx as nx
import osmnx as ox

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# 보행 속도: 성인 평균 보행 4.5 km/h. 게임 중에는 두리번거리므로 낙관적인 값이다.
WALK_KMH = 4.5


def _resolve(*candidates):
    """OSMnx 1.x / 2.x 어느 쪽 이름이든 먼저 찾히는 것을 돌려준다."""
    for cand in candidates:
        obj = ox
        for part in cand.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                break
        if obj is not None:
            return obj
    raise AttributeError("osmnx 에서 %s 를 찾지 못했다 (버전 %s)"
                         % (" / ".join(candidates), ox.__version__))


graph_from_place = _resolve("graph_from_place")
save_graphml = _resolve("io.save_graphml", "save_graphml")
load_graphml = _resolve("io.load_graphml", "load_graphml")
project_graph = _resolve("projection.project_graph", "project_graph")
geocode_to_gdf = _resolve("geocoder.geocode_to_gdf", "geocode_to_gdf")


def cache_path(place):
    """장소 이름 -> 캐시 파일 경로. 공백/쉼표는 파일명에서 빼둔다."""
    slug = place.replace(" ", "").replace(",", "_").replace("/", "_")
    return os.path.join(DATA, slug + "_walk.graphml")


def fetch(place, force=False):
    """`place` 의 보행 그래프를 받아 캐시한다. 이미 있으면 캐시를 읽는다."""
    os.makedirs(DATA, exist_ok=True)
    path = cache_path(place)
    if os.path.exists(path) and not force:
        print("[cache] %s" % os.path.basename(path))
        return load_graphml(path)

    print("[download] %s  (Overpass, 몇 분 걸릴 수 있음)" % place)
    G = graph_from_place(place, network_type="walk")
    save_graphml(G, path)
    print("[saved] %s  (%.1f MB)" % (os.path.basename(path),
                                     os.path.getsize(path) / 1e6))
    return G


def measure(G, place=None):
    """게임판으로서의 특성을 재서 dict 로 돌려준다.

    길이/면적은 UTM 으로 투영한 뒤 재므로 단위는 m 다.
    엣지 길이 합계는 무방향 그래프에서 잰다 — MultiDiGraph 는 양방향 도로를
    엣지 2개로 들고 있어서 그대로 더하면 두 배가 된다.
    """
    Gp = project_graph(G)
    U = nx.MultiGraph(Gp)          # 왕복 엣지를 합쳐 실제 길 길이를 잰다

    lengths = [d["length"] for _, _, d in U.edges(data=True) if "length" in d]
    total_km = sum(lengths) / 1000.0

    xs = [d["x"] for _, d in Gp.nodes(data=True)]
    ys = [d["y"] for _, d in Gp.nodes(data=True)]
    width_km = (max(xs) - min(xs)) / 1000.0
    height_km = (max(ys) - min(ys)) / 1000.0

    deg = dict(U.degree())
    dead_ends = sum(1 for v in deg.values() if v == 1)
    junctions = sum(1 for v in deg.values() if v >= 3)   # 실제 갈림길

    out = {
        "place": place,
        "nodes": G.number_of_nodes(),
        "edges": U.number_of_edges(),
        "total_km": total_km,
        "mean_edge_m": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "width_km": width_km,
        "height_km": height_km,
        "dead_ends": dead_ends,
        "junctions": junctions,
        "crs": str(Gp.graph.get("crs")),
    }

    # 경계 폴리곤 면적 — 없으면 건너뛴다(장소명을 못 받은 경우).
    out["area_km2"] = None
    if place:
        try:
            gdf = geocode_to_gdf(place).to_crs(Gp.graph["crs"])
            out["area_km2"] = float(gdf.area.sum()) / 1e6
        except Exception as e:
            print("  [warn] 면적 계산 실패 (%s): %s" % (place, e))

    # 게임 설계에 직접 쓰이는 파생값
    diag_km = (width_km ** 2 + height_km ** 2) ** 0.5
    out["cross_min"] = diag_km / WALK_KMH * 60.0     # 대각선 종단 도보 시간(분)
    if out["area_km2"]:
        out["junc_per_km2"] = out["junctions"] / out["area_km2"]
    else:
        out["junc_per_km2"] = None
    return out


def report(m):
    """measure() 결과를 사람이 읽는 형태로 출력한다."""
    print("")
    print("=" * 62)
    print("  %s" % m["place"])
    print("=" * 62)
    print("  노드(교차점)      %8d" % m["nodes"])
    print("  엣지(길 구간)     %8d" % m["edges"])
    print("  보행로 총연장     %8.1f km" % m["total_km"])
    print("  평균 구간 길이    %8.1f m" % m["mean_edge_m"])
    if m["area_km2"]:
        print("  면적              %8.1f km2" % m["area_km2"])
    print("  외접 범위         %8.1f x %.1f km" % (m["width_km"], m["height_km"]))
    print("  대각선 종단       %8.0f 분 (도보 %.1f km/h)" % (m["cross_min"], WALK_KMH))
    print("  --- 게임판 관점 ---")
    print("  갈림길(deg>=3)    %8d" % m["junctions"])
    if m["junc_per_km2"]:
        print("  갈림길 밀도       %8.0f 개/km2" % m["junc_per_km2"])
    print("  막다른 길(deg==1) %8d  (%.1f%%)"
          % (m["dead_ends"], 100.0 * m["dead_ends"] / max(m["nodes"], 1)))
