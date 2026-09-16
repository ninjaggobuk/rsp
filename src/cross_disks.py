# -*- coding: utf-8 -*-
"""루트 교차검증 (제대로) — 동일 구성의 '반경 2.5 km 원반' 지도들만 쓴다.

■ 왜 다시 하는가
cross_district.py 는 구 전체 지도를 썼는데, 구 경계에서 잘리는 데다 해상도도
달라서 **같은 석계->공릉 루트가 47.5% vs 27.2% 로 20%p 차이**가 났다. 측정하려던
루트 효과(약 30%p)와 교란이 같은 크기라 결론을 낼 수 없었다.

여기서는 첫 시도 때 받아둔 **동일 방식 원반 지도 4개**만 쓴다. 전부
graph_from_point(중간점, dist=2500, walk) 로 만들어졌으므로 구성이 같다.

■ 경계 효과 통제
원반 반경이 2.5 km 이므로, 양 끝 역이 원반 중심에서 MAX_OFF_M 안에 있어야
채택한다. 그래야 경로 주변에 우회 여유가 비슷하게 남는다.

    python src/cross_disks.py
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path
ensure_conda_dll_path()

import networkx as nx

import cross_district as cd
import rsp_map as rm
import solve_items as si

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

si.MC = 3000

DISKS = [
    "석계역_공릉역_walk.graphml",
    "노원역_중계역_walk.graphml",
    "태릉입구역_화랑대역_walk.graphml",
    "하계역_공릉역_walk.graphml",
]
BAND_KM = (1.2, 2.4)       # 짧은 루트도 포함해 길이 효과를 같이 본다
MAX_OFF_M = 1400           # 원반 중심에서 이 거리 안의 역만 (우회 여유 >= 1.1 km)

CONFIGS = [
    ([0, 0, 0], [0, 0, 0], "기준선"),
    ([0, 0, 2], [0, 0, 1], "재도전 2:1"),
]


def centroid(pos, nodes):
    xs = [pos[n][0] for n in nodes]
    ys = [pos[n][1] for n in nodes]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def main():
    print("동일 구성 원반 지도 %d개로 루트 교차검증 | MC %d판" % (len(DISKS), si.MC))
    print("채택 조건: 양 끝 역이 원반 중심 %dm 이내, 도보 %.1f~%.1f km\n"
          % (MAX_OFF_M, *BAND_KM))

    coords = json.load(open(os.path.join(rm.DATA, "stations.json"),
                            encoding="utf-8"))

    rows = []
    for fname in DISKS:
        path = os.path.join(rm.DATA, fname)
        if not os.path.exists(path):
            print("  [없음] %s" % fname)
            continue
        Gc, S, pos = cd.district_graph(fname)
        cx, cy = centroid(pos, list(S.nodes()))
        tag = fname.replace("_walk.graphml", "")

        inside = {}
        for name, (lat, lon) in coords.items():
            node, snapd = cd.snap(Gc, lat, lon)
            if snapd > 400 or node not in S:
                continue
            off = ((pos[node][0] - cx) ** 2 + (pos[node][1] - cy) ** 2) ** 0.5
            if off <= MAX_OFF_M:
                inside[name] = node
        print("  [%s] 노드 %d | 중심 %dm 안의 역 %d개: %s"
              % (tag, S.number_of_nodes(), MAX_OFF_M, len(inside),
                 ", ".join(sorted(inside))))

        for a, b in itertools.combinations(sorted(inside), 2):
            na, nb = inside[a], inside[b]
            if na == nb:
                continue
            comp = nx.node_connected_component(S, nb)
            if na not in comp:
                continue
            Ssub = S.subgraph(comp).copy()
            t = nx.shortest_path_length(Ssub, na, nb, weight="w")
            km = t * si.WALK_KMH / 60.0
            if not (BAND_KM[0] <= km <= BAND_KM[1]):
                continue
            rows.append((tag, a, b, Ssub, pos, na, nb, km, t))

    if not rows:
        print("\n조건에 맞는 루트가 없다.")
        return

    print("\n  채택 루트 %d개\n" % len(rows))
    print("  지도                루트                      거리   도보  | "
          + "  ".join("%-12s" % c[2] for c in CONFIGS))
    print("  " + "-" * 92)
    results = {i: [] for i in range(len(CONFIGS))}
    for tag, a, b, S, pos, na, nb, km, t in rows:
        V = si.solve(S, nb, p_shadow=2 / 6.0)
        cells = []
        for i, (e, se, _note) in enumerate(CONFIGS):
            _, r90, _ = si.rate(S, pos, V, na, nb, e, se, 40.0,
                                n_exp=4, n_sha=2)
            results[i].append(r90)
            cells.append("%11.1f%%" % (100 * r90))
        print("  %-18s %-10s->%-10s %5.2fkm %5.1f분 | %s"
              % (tag[:18], a[:10], b[:10], km, t, "  ".join(cells)))

    print("\n  === 루트 간 산포 (4:2, 90분) ===")
    for i, (_e, _se, note) in enumerate(CONFIGS):
        v = results[i]
        print("  %-12s  %.1f%% ~ %.1f%%   폭 %.1f%%p"
              % (note, 100 * min(v), 100 * max(v), 100 * (max(v) - min(v))))


if __name__ == "__main__":
    main()
