# -*- coding: utf-8 -*-
"""팀이 '짜고' 내면 승률이 바뀌는가 — 4:2 를 중심으로.

앞선 probe_rps_balance.py 는 전원이 독립 균등으로 낸다고 가정했다. 하지만 두 팀은
갈림길 앞에 같이 서 있으므로 미리 합을 맞출 수 있다. 여기서는 세 가지 팀 전략을
교차시켜 그 가정이 깨지는지 본다.

  iid    : 팀원 각자 독립 균등 (기준)
  same   : 팀원 전원이 같은 기호 (그 라운드에 하나를 공유)
  spread : 팀원이 서로 다른 기호로 갈라짐 (살아있는 인원에 0,1,2 순환 배정)

★ spread 는 살아있는 팀원이 3명 이상이면 매 라운드 세 기호가 전부 나오므로
   **무조건 무승부** — 갈림길이 영원히 안 끝난다. 규칙 구멍이다.

    python src/probe_rps_coord.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rps

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TRIALS = 100000
STRATS = ["iid", "same", "spread"]
MAX_ROUNDS = 300          # 이걸 넘으면 '교착'으로 센다


def make_thrower(team_of, strategies, rng):
    """플레이어별 throw 콜백. 라운드마다 팀 단위 결정을 캐시한다."""
    cache = {}

    def throw(p, alive, rnd):
        t = team_of[p]
        key = (t, rnd)
        if key not in cache:
            mates = [q for q in alive if team_of[q] == t]
            st = strategies[t]
            if st == "iid":
                cache[key] = {q: rng.randrange(3) for q in mates}
            elif st == "same":
                s = rng.randrange(3)
                cache[key] = {q: s for q in mates}
            elif st == "spread":
                off = rng.randrange(3)
                cache[key] = {q: (off + i) % 3 for i, q in enumerate(mates)}
            else:
                raise ValueError(st)
        return cache[key][p]

    return throw


def run(n_exp, n_sha, st_exp, st_sha, trials=TRIALS, seed=999):
    rng = random.Random(seed)
    team_of = [0] * n_exp + [1] * n_sha          # 0=원정대 1=쉐도우
    n = n_exp + n_sha
    sha_wins = 0
    stuck = 0
    rounds_sum = 0
    resolved = 0
    for _ in range(trials):
        throw = make_thrower(team_of, {0: st_exp, 1: st_sha}, rng)
        try:
            w, r = rps.play_junction(n, rng, throw=throw, max_rounds=MAX_ROUNDS)
        except RuntimeError:
            stuck += 1
            continue
        resolved += 1
        rounds_sum += r
        if team_of[w] == 1:
            sha_wins += 1
    return {
        "sha_rate": (sha_wins / resolved) if resolved else float("nan"),
        "stuck": stuck / trials,
        "mean_rounds": (rounds_sum / resolved) if resolved else float("nan"),
    }


def table(n_exp, n_sha):
    print("\n  === 원정대 %d : 쉐도우 %d ===" % (n_exp, n_sha))
    print("  기준(양팀 iid) 쉐도우 승률 = %.2f%%\n" % (100.0 * n_sha / (n_exp + n_sha)))
    print("  원정대 \\ 쉐도우 |" + "".join("  %-22s" % s for s in STRATS))
    print("  " + "-" * 76)
    for se in STRATS:
        cells = []
        for ss in STRATS:
            r = run(n_exp, n_sha, se, ss)
            if r["stuck"] > 0.5:
                cells.append("  교착 %.0f%%            " % (100 * r["stuck"]))
            else:
                cells.append("  %5.1f%%  (%4.1f라운드)   "
                             % (100 * r["sha_rate"], r["mean_rounds"]))
        print("  %-15s |" % se + "".join(cells))


def main():
    print("팀 전략 교차 — 표 안의 값은 '쉐도우 승률 (갈림길당 평균 라운드)'")
    print("%d회 시뮬, 교착 판정 %d라운드" % (TRIALS, MAX_ROUNDS))
    for e, s in [(4, 2), (2, 1), (6, 3)]:
        table(e, s)


if __name__ == "__main__":
    main()
