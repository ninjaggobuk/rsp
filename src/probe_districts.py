# -*- coding: utf-8 -*-
"""노원구 / 성북구 보행 네트워크를 받아서 재고 그린다.

목적은 하나다 — 이 동네가 RSP 게임판으로 쓸 만한지 눈과 숫자로 판단하는 것.
받은 그래프는 data/ 에 캐시되므로 다시 돌려도 재다운로드하지 않는다.

    python src/probe_districts.py

환경변수 PLACES 로 다른 동네를 넣을 수 있다 (쉼표 구분).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _envpath import ensure_conda_dll_path      # matplotlib 보다 먼저 (docstring 참조)
ensure_conda_dll_path()

import matplotlib
matplotlib.use("Agg")                     # 헤드리스 렌더
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

import rsp_map as rm

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = rm.ROOT
FIGS = os.path.join(ROOT, "figs")

DEFAULT_PLACES = ["노원구, 서울특별시, 대한민국", "성북구, 서울특별시, 대한민국"]
# 장소명 안에 쉼표가 들어가므로 여러 장소는 ';' 로 구분한다.
PLACES = [p.strip() for p in os.environ.get("PLACES", ";".join(DEFAULT_PLACES)).split(";")
          if p.strip()] or DEFAULT_PLACES

# 전역 그림 규칙: Times New Roman, 수식 stix, 최종 인쇄 크기에서 9pt 이상.
plt.rcParams.update({
    "font.family": "Times New Roman",
    "mathtext.fontset": "stix",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "savefig.dpi": 300,
})
# 한글 라벨이 Times 에 없으므로 폴백을 붙인다(Times 가 우선, 없는 글자만 맑은고딕).
plt.rcParams["font.family"] = ["Times New Roman", "Malgun Gothic"]


def edge_segments(Gp):
    """투영된 그래프의 엣지를 LineCollection 용 좌표열로 변환한다."""
    segs = []
    for u, v, d in Gp.edges(data=True):
        geom = d.get("geometry")
        if geom is not None:
            segs.append(list(geom.coords))
        else:
            segs.append([(Gp.nodes[u]["x"], Gp.nodes[u]["y"]),
                         (Gp.nodes[v]["x"], Gp.nodes[v]["y"])])
    return segs


def scale_bar(ax, length_m=1000):
    """축 좌하단에 축척 막대를 그린다 (좌표가 m 단위이므로 그대로 쓴다)."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    pad_x = (x1 - x0) * 0.06
    pad_y = (y1 - y0) * 0.06
    xs = x0 + pad_x
    ys = y0 + pad_y
    ax.plot([xs, xs + length_m], [ys, ys], color="black", lw=1.6,
            solid_capstyle="butt", zorder=5)
    ax.text(xs + length_m / 2.0, ys + (y1 - y0) * 0.012,
            "%d km" % (length_m // 1000), ha="center", va="bottom",
            fontsize=9, zorder=5)


def main():
    os.makedirs(FIGS, exist_ok=True)
    print("osmnx %s" % rm.ox.__version__)

    results = []
    for place in PLACES:
        G = rm.fetch(place)
        m = rm.measure(G, place)
        rm.report(m)
        results.append((place, G, m))

    # --- 그림: 구별 1패널, 2단 폭(7.1 in)에 나란히 ---
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(7.1, 4.0))
    if n == 1:
        axes = [axes]

    for ax, (place, G, m) in zip(axes, results):
        Gp = rm.project_graph(G)
        segs = edge_segments(Gp)
        lc = LineCollection(segs, linewidths=0.18, colors="#1a1a1a", alpha=0.85)
        ax.add_collection(lc)

        xs = [d["x"] for _, d in Gp.nodes(data=True)]
        ys = [d["y"] for _, d in Gp.nodes(data=True)]
        ax.set_xlim(min(xs), max(xs))       # 데이터에 딱 맞춰 여백 없음
        ax.set_ylim(min(ys), max(ys))
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_linewidth(0.8)

        short = place.split(",")[0].strip()
        ax.set_title("%s\n%.0f km 보행로 · 갈림길 %s개 · 종단 %.0f분"
                     % (short, m["total_km"], format(m["junctions"], ","),
                        m["cross_min"]), fontsize=9, linespacing=1.4)
        scale_bar(ax)

    fig.tight_layout()
    out = os.path.join(FIGS, "districts_walk.png")
    fig.savefig(out, bbox_inches="tight")
    print("\n[fig] %s" % out)


if __name__ == "__main__":
    main()
