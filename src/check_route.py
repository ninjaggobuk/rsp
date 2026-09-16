# -*- coding: utf-8 -*-
"""루트 체커 — 출발/도착 지점을 넣으면 그 루트가 공정한지 알려준다.

■ 왜 필요한가 (2026-09-17 결론)
아이템은 중앙값만 옮기고 **루트 간 30%p 격차는 못 줄인다**. 그런데 지형 특징으로
난이도를 예측하려 했더니 가장 강한 지표(갈림길 수)도 r = -0.40, 변동의 16%만
설명했다. **눈으로 판단하는 규칙은 만들 수 없다.**
그래서 남은 방법은 하나 — 루트를 하나씩 직접 재는 것. 이 스크립트가 그 일을 한다.

■ 쓰는 법
    python src/check_route.py --from "37.6315,127.0777" --to "37.6255,127.0730"
    python src/check_route.py --from 서울과학기술대학교 --to 공릉역

좌표는 네이버/구글 지도에서 우클릭하면 나온다. 지오코딩이 자주 실패하므로
**좌표를 직접 넣는 쪽이 확실하다**.

■ 읽는 법
90분 도착률이 45~55%면 공정한 루트다. 그 밖이면 지점을 조금 옮겨서 다시 재보면
된다. '치명적 갈림길'은 그 자리에서 지면 손해가 가장 큰 교차로 — 아이템을 쓸
자리이자, 구경하기 좋은 승부처다.
"""
import argparse
import json
import math
import os
import sys
import time

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

si.MC = 2000                  # 오차 ±2.2%p
MAX_SNAP_M = 400              # 지점이 이보다 멀리 떨어진 노드에 붙으면 지도 밖
MIN_MARGIN_M = 1100           # 지점 주변에 최소 이만큼 지도가 남아야 우회가 잘리지 않음
NEAR_PATH_M = 600.0           # '치명적 갈림길'을 찾을 경로 주변 반경

ALLOCS = [
    ([0, 0, 1], [0, 0, 1], "재도전 1:1  (권고)"),
    ([0, 0, 0], [0, 0, 0], "아이템 없음"),
    ([0, 0, 2], [0, 0, 1], "재도전 2:1"),
]


def parse_point(s):
    """'37.62,127.07' 이면 좌표로, 아니면 장소명으로 본다."""
    if "," in s:
        try:
            lat, lon = [float(v) for v in s.split(",", 1)]
            return (lat, lon), "좌표"
        except ValueError:
            pass
    cache_path = os.path.join(rm.DATA, "stations.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        if s in cache:
            return tuple(cache[s]), "캐시"
    geocode = rm._resolve("geocode", "geocoder.geocode")
    for i in range(3):
        try:
            lat, lon = geocode(s + ", 서울")
            return (lat, lon), "지오코딩"
        except Exception as e:
            print("  [retry %d/3] 지오코딩 %s : %s" % (i + 1, s, type(e).__name__))
            time.sleep(3)
    raise SystemExit("지점을 찾지 못했다: %s  (좌표로 직접 넣어 보십시오)" % s)


def pick_graph(p_from, p_to):
    """캐시된 지도 중 두 지점을 여유 있게 담는 것을 고른다."""
    best = None
    for fname in sorted(os.listdir(rm.DATA)):
        if not fname.endswith(".graphml"):
            continue
        try:
            Gc, S, pos = cd.district_graph(fname)
        except Exception:
            continue
        S = S.subgraph(max(nx.connected_components(S), key=len)).copy()
        xs = [pos[n][0] for n in S]
        ys = [pos[n][1] for n in S]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        radius = max(math.hypot(pos[n][0] - cx, pos[n][1] - cy) for n in S)

        ok, snapped, margin = True, [], 1e9
        for lat, lon in (p_from, p_to):
            node, d = cd.snap(Gc, lat, lon)
            if d > MAX_SNAP_M or node not in S:
                ok = False
                break
            off = math.hypot(pos[node][0] - cx, pos[node][1] - cy)
            margin = min(margin, radius - off)
            snapped.append(node)
        if not ok or snapped[0] == snapped[1]:
            continue
        if not nx.has_path(S, snapped[0], snapped[1]):
            continue
        if margin < MIN_MARGIN_M:
            continue
        # ★ 여유가 충분한 것들 중에서는 **해상도가 높은** 지도를 고른다.
        #   구 전체 지도는 산지가 섞여 노드 밀도가 낮고 경계가 잘려 있어
        #   같은 루트도 원정대 승률이 20%p 부풀려진다 (2026-09-17 통제실험).
        area_km2 = math.pi * (radius / 1000.0) ** 2
        density = S.number_of_nodes() / max(area_km2, 1e-6)
        if best is None or density > best[0]:
            best = (density, margin, fname, Gc, S, pos, snapped[0], snapped[1])
    return best


def to_latlon(Gc, x, y):
    g = gpd.GeoDataFrame(geometry=[Point(x, y)],
                         crs=Gc.graph["crs"]).to_crs("EPSG:4326")
    return g.geometry[0].y, g.geometry[0].x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--to", dest="dst", required=True)
    ap.add_argument("--top", type=int, default=5, help="보여줄 치명적 갈림길 수")
    args = ap.parse_args()

    p_from, how_f = parse_point(args.src)
    p_to, how_t = parse_point(args.dst)
    print("출발  %-22s %.5f, %.5f  (%s)" % (args.src, p_from[0], p_from[1], how_f))
    print("도착  %-22s %.5f, %.5f  (%s)" % (args.dst, p_to[0], p_to[1], how_t))

    picked = pick_graph(p_from, p_to)
    if picked is None:
        raise SystemExit(
            "\n두 지점을 모두 담는 캐시 지도가 없다.\n"
            "  data/ 에 해당 지역 보행망을 먼저 받아야 한다 "
            "(rsp_map.fetch 또는 graph_from_point).")
    density, margin, fname, Gc, S, pos, a, b = picked
    # density 는 외접원 기준이라 절대값은 과소평가된다. 지도끼리 고르는
    # 상대 점수로만 쓴다 (원반 > 구 전체).
    print("\n지도  %s\n      여유 %.0f m | 상대 해상도 %.0f (높을수록 세밀)"
          % (fname, margin, density))

    walk = nx.shortest_path_length(S, a, b, weight="w")
    path = nx.shortest_path(S, a, b, weight="w")
    njunc = sum(1 for n in path[:-1] if S.degree(n) >= 3)
    print("\n도보  %.2f km / %.1f 분   |   경로상 갈림길 %d 개"
          % (walk / 60.0 * si.WALK_KMH, walk, njunc))

    V = si.solve(S, b, p_shadow=2 / 6.0)

    print("\n  구성                     60분 도착   90분 도착   판정")
    print("  " + "-" * 58)
    verdict_main = None
    for e, se, note in ALLOCS:
        r60, r90, _med = si.rate(S, pos, V, a, b, e, se, 40.0, n_exp=4, n_sha=2)
        if 0.45 <= r90 <= 0.55:
            v = "공정"
        elif r90 < 0.45:
            v = "쉐도우 유리"
        else:
            v = "원정대 유리"
        if verdict_main is None:
            verdict_main = (r90, v)
        print("  %-22s %7.1f%%    %7.1f%%    %s"
              % (note, 100 * r60, 100 * r90, v))

    r90, v = verdict_main
    print("\n  >> 권고 구성(재도전 1:1) 기준 이 루트는 **%s** (90분 %.1f%%)"
          % (v, 100 * r90))
    if v != "공정":
        print("     지점을 200~400 m 옮겨서 다시 재보면 대개 달라진다.")

    # 치명적 갈림길 — 지면 손해가 큰 순서.
    # ★ 경로 주변으로 한정한다. 지도 전체에서 뽑으면 일행이 갈 일도 없는
    #   먼 동네 교차로가 올라온다.
    near = set()
    r2 = NEAR_PATH_M ** 2
    for n in S:
        x, y = pos[n]
        for p in path:
            if (x - pos[p][0]) ** 2 + (y - pos[p][1]) ** 2 <= r2:
                near.add(n)
                break

    rows = []
    for (prev, cur) in V:
        if cur == b or cur not in near:
            continue
        opts = si.options(S, prev, cur)
        if len(opts) < 2:
            continue
        vals = [S[cur][w]["w"] + V[(cur, w)] for w in opts]
        rows.append((max(vals) - min(vals), cur, len(opts)))
    seen, top = set(), []
    for d, cur, k in sorted(rows, reverse=True):
        if cur in seen:
            continue
        seen.add(cur)
        top.append((d, cur, k))
        if len(top) >= args.top:
            break

    print("\n  === 치명적 갈림길 %d곳 (여기서 지면 손해가 가장 크다) ===" % len(top))
    print("  손해(분)  갈래  위도, 경도                지도 링크")
    for d, cur, k in top:
        lat, lon = to_latlon(Gc, pos[cur][0], pos[cur][1])
        print("  %7.1f   %2d   %.5f, %.5f   https://map.naver.com/p?c=%.5f,%.5f,17,0,0,0,dh"
              % (d, k, lat, lon, lon, lat))


if __name__ == "__main__":
    main()
