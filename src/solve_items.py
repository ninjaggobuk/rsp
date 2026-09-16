# -*- coding: utf-8 -*-
"""아이템 분배안 — 양 팀이 모두 아이템을 갖는 4:2 기준.

■ 보정 근거 (2026-09-17 사장님 실측)
  갈림길 수   한 판 20~30번          -> consolidate tolerance 25 m (모델 24.7)
  갈림길 소요 25초 안팎               -> 6.2라운드이므로 라운드당 4초
  전적        6판 중 원정대 1승(16.7%) -> 모델 기준선 13.2%(60분)/26.6%(90분) 와 정합
  U턴         즉시 되돌아가기만 금지   -> 상태 (직전, 현재) 로 반영
  재도전권    가위바위보를 지고 나서 사용 (확정)

■ 아이템 (양 팀 공통, 개수만 다르게 줄 수 있다)
  1 무조건승리 : 가위바위보 없이 그 갈림길을 가져간다        (선언: 가위바위보 전)
  2 스킵·직진  : 지금 이 갈림길의 가위바위보를 건너뛰고 직진 (선언: 가위바위보 전)
                 ★ 2026-09-17 사장님 설명으로 해석 정정. 처음엔 '다음 갈림길에서
                   눈감고 직진'으로 잘못 짜서 -9.7%p 라는 엉뚱한 값이 나왔다.
                   실제로는 횡단보도를 건너 그 갈림길에 서서, 직진이 유리한 것을
                   **보고** 쓰는 것이라 손해가 날 수 없다.
  3 재도전권   : 졌을 때 그 갈림길을 한 번 다시               (사용: 지고 나서)

■ 확정된 세부 규칙 (사장님 2026-09-17)
  - '무조건승리' 동시 선언 시 타이브레이크. 진 쪽은 그 턴에 못 쓸 뿐 **개수는 유지**.
      tiebreak="rep" 현행: 팀 대표 1:1 -> 50/50
      tiebreak="all" 제안: 전원 가위바위보 -> 원정대 n_exp/(n_exp+n_sha)
  - 재도전권은 **갈림길당 1회** (연속 사용 금지).
  - 쉐도우의 '스킵·직진'은 직진이 원정대에게 최악일 때만 선언한다(그게 합리적).

■ 정책
  아이템은 Δ >= θ 인 갈림길에서만 쓴다. θ=0 은 '보이면 바로', θ=40 은 '치명적인
  자리까지 아낀다'. Δ 중앙값이 약 20분이라 θ 20 이하는 사실상 즉시 사용과 같다.

    python src/solve_items.py
"""
import math
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

WALK_KMH = 4.0
N_EXP, N_SHA = 4, 2
P_SHADOW = N_SHA / float(N_EXP + N_SHA)
SEC_PER_ROUND = 4.0
TOLERANCE = 25
LIMIT_BASE, LIMIT_EXT = 60.0, 90.0
MC = 4000
TIME_CAP = 300.0
TOL_VI, MAX_SWEEP = 1e-7, 20000
T_RPS_NOM = 6.23 * SEC_PER_ROUND / 60.0

consolidate = rm._resolve("simplification.consolidate_intersections",
                          "consolidate_intersections")
geocode = rm._resolve("geocode", "geocoder.geocode")
nearest_nodes = rm._resolve("distance.nearest_nodes", "nearest_nodes")


def build():
    G = rm.load_graphml(os.path.join(rm.DATA, "seokgye_gongneung_walk.graphml"))
    Gp = rm.project_graph(G)
    Gc = consolidate(Gp, tolerance=TOLERANCE, rebuild_graph=True, dead_ends=True)
    S = nx.Graph()
    for u, v, d in nx.MultiGraph(Gc).edges(data=True):
        if u == v:
            continue
        w = d.get("length", 0.0) / 1000.0 / WALK_KMH * 60.0
        if not S.has_edge(u, v) or w < S[u][v]["w"]:
            S.add_edge(u, v, w=w)
    pos = {n: (d["x"], d["y"]) for n, d in Gc.nodes(data=True)}
    s_ll, g_ll = geocode("석계역, 서울"), geocode("공릉역, 서울")
    pts = gpd.GeoDataFrame(
        geometry=[Point(s_ll[1], s_ll[0]), Point(g_ll[1], g_ll[0])],
        crs="EPSG:4326").to_crs(Gc.graph["crs"])
    start = nearest_nodes(Gc, pts.geometry[0].x, pts.geometry[0].y)
    goal = nearest_nodes(Gc, pts.geometry[1].x, pts.geometry[1].y)
    S = S.subgraph(nx.node_connected_component(S, goal)).copy()
    globals()['POS'] = pos
    return S, pos, start, goal


BEARING_BUCKET = 25.0     # 이 각도 안이면 '같은 방향'으로 본다
POS = None                # 현재 그래프의 노드 좌표 (build 계열이 채운다)


def option_groups(S, prev, cur):
    """갈림길에서 고를 수 있는 '방향'들. 각 방향은 그 방향의 길 묶음이다.

    ★ OSM 엣지를 그대로 세면 안 된다. 교차로 병합 때문에 역 일대가 한 점이
      되면서 엣지가 34개까지 붙는데(2026-09-17 실측), 실제로는 동/서/남/북 +
      골목 몇 개다. 사장님 규칙도 "직진 횡단보도 1, 우측 횡단보도 1, 좌측 보도
      1 = 3갈래"처럼 **방향**으로 센다.

    ★ 대표를 미리 하나 고르면 안 된다. '가장 짧은 길'로 골랐더니 5 m 짜리
      횡단보도 토막이 80 m 진짜 도로를 밀어냈고, 목적지로 가는 길이 선택지에서
      사라져 **도착 확률 0%** 인 루트가 생겼다(2026-09-17 실측).
      그래서 묶음을 그대로 돌려주고, 값은 '그 방향으로 가면 자연히 택할 최선'
      (묶음 안 최솟값)으로 친다. 양 팀이 같은 값을 보므로 공평하고, 목적지로
      가는 길이 들어 있는 묶음은 값이 낮아 반드시 살아남는다.
    """
    opts = [w for w in S[cur] if w != prev]
    if not opts:
        return [[prev]] if prev is not None else []
    if POS is None or len(opts) <= 2:
        return [[w] for w in opts]

    items = []
    for w in opts:
        ang = math.degrees(math.atan2(POS[w][1] - POS[cur][1],
                                      POS[w][0] - POS[cur][0])) % 360.0
        items.append((ang, w))
    items.sort()

    groups, g = [], [items[0]]
    for it in items[1:]:
        if it[0] - g[-1][0] <= BEARING_BUCKET:
            g.append(it)
        else:
            groups.append(g); g = [it]
    groups.append(g)
    if len(groups) > 1 and (360.0 - groups[-1][-1][0]) + groups[0][0][0] <= BEARING_BUCKET:
        groups[0] = groups[-1] + groups[0]
        groups.pop()

    return [[w for _a, w in gr] for gr in groups]


def group_pick(S, V, cur, group):
    """그 방향으로 갈 때 자연히 택하는 길 = 묶음 안에서 남은 시간이 최소인 길."""
    best, bv = group[0], float("inf")
    for w in group:
        v = S[cur][w]["w"] + V[(cur, w)]
        if v < bv:
            bv, best = v, w
    return best, bv


def options(S, prev, cur):
    """묶음별 대표 하나씩 (V 를 모를 때 쓰는 근사 — 가장 짧은 길)."""
    return [min(gr, key=lambda w: S[cur][w]["w"]) for gr in option_groups(S, prev, cur)]


def solve(S, goal, t_rps=T_RPS_NOM, p_shadow=P_SHADOW):
    states = [(u, v) for u, v in S.edges()] + [(v, u) for u, v in S.edges()]
    V = {s: 0.0 for s in states}
    for _ in range(MAX_SWEEP):
        delta = 0.0
        for (prev, cur) in states:
            if cur == goal:
                continue
            grs = option_groups(S, prev, cur)
            vals = [group_pick(S, V, cur, gr)[1] for gr in grs]
            new = (t_rps + (1 - p_shadow) * min(vals) + p_shadow * max(vals)
                   if len(grs) >= 2 else vals[0])
            delta = max(delta, abs(new - V[(prev, cur)]))
            V[(prev, cur)] = new
        if delta < TOL_VI:
            break
    return V


def straight(pos, prev, cur, opts):
    if prev is None:
        return opts[0]
    h = math.atan2(pos[cur][1] - pos[prev][1], pos[cur][0] - pos[prev][0])
    best, bd = opts[0], 9e9
    for w in opts:
        a = math.atan2(pos[w][1] - pos[cur][1], pos[w][0] - pos[cur][0])
        dd = abs((a - h + math.pi) % (2 * math.pi) - math.pi)
        if dd < bd:
            bd, best = dd, w
    return best


def play(S, pos, V, start, goal, rng, exp, sha, theta,
         n_exp=N_EXP, n_sha=N_SHA, tiebreak="all"):
    """exp/sha = [무조건승리, 스킵직진, 재도전권] 개수. 소모는 지역 사본에서."""
    ew, es, er = exp
    sw, ss, sr = sha
    prev, cur = None, start
    t = 0.0
    n_r = n_exp + n_sha

    while cur != goal and t < TIME_CAP:
        grs = option_groups(S, prev, cur)
        if not grs:
            break
        if len(grs) == 1:
            nxt = group_pick(S, V, cur, grs[0])[0]
            t += S[cur][nxt]["w"]
            prev, cur = cur, nxt
            continue

        picked = [group_pick(S, V, cur, gr) for gr in grs]
        vals = [(v, w) for w, v in picked]
        opts = [w for w, _v in picked]
        best, worst = min(vals), max(vals)
        d = worst[0] - best[0]

        hot = d >= theta
        st_node = straight(pos, prev, cur, opts)

        # 아이템2 '스킵·직진' — 지금 이 갈림길에 서서 직진이 내게 유리하면,
        # 가위바위보 없이 그대로 직진한다(사장님 2026-09-17 설명: 횡단보도를 건넌
        # 뒤 그 방향으로 계속 가야 할 때 쓴다). 보고 쓰는 것이므로 손해가 없고,
        # 가위바위보 시간도 아낀다. 직진이 내 최선일 때만 발동하므로 아이템1 보다
        # 약하다 — 대신 아이템1 은 직진이 아닌 자리를 위해 아껴둘 수 있다.
        if es > 0 and hot and st_node == best[1]:
            es -= 1
            nxt = best[1]
            t += S[cur][nxt]["w"]
            prev, cur = cur, nxt
            continue
        if ss > 0 and hot and st_node == worst[1]:
            ss -= 1
            nxt = worst[1]
            t += S[cur][nxt]["w"]
            prev, cur = cur, nxt
            continue

        e_win = ew > 0 and hot
        s_win = sw > 0 and hot
        if e_win and s_win:
            # 동시 선언 타이브레이크. 진 쪽은 '그 턴에 사용 불가'일 뿐
            # 개수는 차감되지 않는다 (사장님 2026-09-17).
            if tiebreak == "rep":          # 현행: 팀 대표 1:1 -> 50/50
                _, rr = rps.play_junction(2, rng)
                t += rr * SEC_PER_ROUND / 60.0
                exp_gets = rng.random() < 0.5
            else:                          # 제안: 전원 -> 원정대 n_exp/(n_exp+n_sha)
                wi, rr = rps.play_junction(n_r, rng)
                t += rr * SEC_PER_ROUND / 60.0
                exp_gets = wi < n_exp
            if exp_gets:
                s_win = False
            else:
                e_win = False

        if e_win:
            ew -= 1
            nxt = best[1]
        elif s_win:
            sw -= 1
            nxt = worst[1]
        else:
            w_idx, rounds = rps.play_junction(n_r, rng)
            t += rounds * SEC_PER_ROUND / 60.0
            lost_exp = w_idx >= n_exp

            if lost_exp and er > 0 and hot:              # 원정대 재도전
                er -= 1
                w_idx, rounds = rps.play_junction(n_r, rng)
                t += rounds * SEC_PER_ROUND / 60.0
                lost_exp = w_idx >= n_exp
            elif (not lost_exp) and sr > 0 and hot:      # 쉐도우 재도전
                sr -= 1
                w_idx, rounds = rps.play_junction(n_r, rng)
                t += rounds * SEC_PER_ROUND / 60.0
                lost_exp = w_idx >= n_exp

            nxt = worst[1] if lost_exp else best[1]

        t += S[cur][nxt]["w"]
        prev, cur = cur, nxt
    return t


def rate(S, pos, V, start, goal, exp, sha, theta, seed=7,
         n_exp=N_EXP, n_sha=N_SHA, tiebreak="all"):
    rng = random.Random(seed)
    ts = [play(S, pos, V, start, goal, rng, exp, sha, theta,
               n_exp, n_sha, tiebreak) for _ in range(MC)]
    return (sum(1 for x in ts if x <= LIMIT_BASE) / len(ts),
            sum(1 for x in ts if x <= LIMIT_EXT) / len(ts),
            st.median(ts))


def fmt(v):
    return "%d/%d/%d" % tuple(v)


EXP_SET = [
    ([0, 0, 1], "재도전1"),
    ([0, 0, 2], "재도전2"),
    ([0, 1, 1], "직진1+재도전1"),
    ([1, 0, 1], "승리1+재도전1"),
    ([1, 1, 1], "승리1+직진1+재도전1"),
    ([1, 1, 2], "승리1+직진1+재도전2"),
]
SHA_SET = [
    ([0, 0, 0], "없음"),
    ([0, 1, 0], "직진1만  <-- 나온 의견"),
    ([0, 0, 1], "재도전1만"),
    ([1, 1, 1], "각 1개"),
]


def band(r90):
    return " <<<" if 0.45 <= r90 <= 0.55 else ""


def grid(S, pos, V, start, goal, n_e, n_s, tiebreak="all"):
    print("  원정대(승/직/재)      쉐도우        | 90분 θ=40  θ=0  | 편차 | 60분 θ=40")
    print("  " + "-" * 76)
    for se, sname in SHA_SET:
        for e, ename in EXP_SET:
            a60, a90, _ = rate(S, pos, V, start, goal, e, se, 40.0,
                               n_exp=n_e, n_sha=n_s, tiebreak=tiebreak)
            _, b90, _ = rate(S, pos, V, start, goal, e, se, 0.0,
                             n_exp=n_e, n_sha=n_s, tiebreak=tiebreak)
            print("  %-7s %-13s %-13s | %6.1f%% %6.1f%% | %4.1f | %6.1f%%%s"
                  % (fmt(e), ename, sname if e is EXP_SET[0][0] else "",
                     100 * a90, 100 * b90, abs(100 * (a90 - b90)), 100 * a60,
                     band(a90)))
        print("  " + "-" * 76)


def main():
    print("tol %dm | 라운드당 %.0f초 | MC %d판 | <<< = 90분 45~55%%"
          % (TOLERANCE, SEC_PER_ROUND, MC))
    S, pos, start, goal = build()
    free = nx.shortest_path_length(S, start, goal, weight="w")
    print("  노드 %d / 엣지 %d | 방해 없는 도보 %.1f분"
          % (S.number_of_nodes(), S.number_of_edges(), free))

    for n_e, n_s in ((4, 2), (5, 2)):
        p_s = n_s / float(n_e + n_s)
        V = solve(S, goal, p_shadow=p_s)
        b40 = rate(S, pos, V, start, goal, [0, 0, 0], [0, 0, 0], 40.0,
                   n_exp=n_e, n_sha=n_s)
        print("")
        print("############ %d : %d  (쉐도우 갈림길승률 %.1f%%) ############"
              % (n_e, n_s, 100 * p_s))
        print("  아이템 없음 기준선: 60분 %.1f%% / 90분 %.1f%%"
              % (100 * b40[0], 100 * b40[1]))
        print("")
        grid(S, pos, V, start, goal, n_e, n_s)

    # 타이브레이크 규칙 비교 — 양 팀이 모두 '무조건승리'를 가진 경우에만 발동한다
    print("")
    print("############ 타이브레이크 규칙 (양팀 다 무조건승리 보유 시) ############")
    V4 = solve(S, goal, p_shadow=2 / 6.0)
    print("  원정대   쉐도우  | 대표1:1(현행)  전원6인(제안) |  차이")
    print("  " + "-" * 60)
    for e in ([1, 1, 1], [1, 0, 1], [2, 1, 1]):
        for se in ([1, 1, 1], [1, 0, 1]):
            _, r_rep, _ = rate(S, pos, V4, start, goal, e, se, 40.0,
                               n_exp=4, n_sha=2, tiebreak="rep")
            _, r_all, _ = rate(S, pos, V4, start, goal, e, se, 40.0,
                               n_exp=4, n_sha=2, tiebreak="all")
            print("  %-8s %-7s | %11.1f%% %13.1f%% | %+5.1f%%p"
                  % (fmt(e), fmt(se), 100 * r_rep, 100 * r_all,
                     100 * (r_all - r_rep)))


if __name__ == "__main__":
    main()
