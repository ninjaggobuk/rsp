# -*- coding: utf-8 -*-
"""브라우저판 빌드 — 템플릿에 지도 JSON 을 주입한다.

web/game.template.html 의 __MAP_JSON__ 자리에 web/gongneung.json 을 통째로 넣어
  web/game.html   (아트팩트 게시용)
  docs/index.html (GitHub Pages 용 — Pages 소스를 main 브랜치 /docs 로 설정)
두 곳에 같은 내용을 쓴다.

JSON 을 파일로 분리해 두는 이유: 71 KB 짜리 좌표 덩어리를 템플릿에 박아두면
게임 코드를 고칠 때마다 diff 가 못 읽게 된다.

    python src/build_web.py
"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL = os.path.join(ROOT, "web", "game.template.html")
MAP = os.path.join(ROOT, "web", "gongneung.json")
OUTS = [os.path.join(ROOT, "web", "game.html"),
        os.path.join(ROOT, "docs", "index.html")]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    tpl = io.open(TPL, encoding="utf-8").read()
    mj = io.open(MAP, encoding="utf-8").read()

    if "__MAP_JSON__" not in tpl:
        raise SystemExit("템플릿에 __MAP_JSON__ 자리표시자가 없다")
    # JSON 안에 </script> 가 있으면 인라인 블록이 조기 종료된다
    if "</script" in mj.lower():
        raise SystemExit("지도 JSON 안에 script 종료 태그가 있다")

    # 템플릿에 남은 옛 캔버스 시절 식별자 — 있으면 런타임에 터진다
    for dead in ("sizeCanvas", "getContext", "cv.", "nearestNode("):
        if dead in tpl:
            raise SystemExit("템플릿에 죽은 참조가 남아 있다: %s" % dead)

    body = tpl.replace("__MAP_JSON__", mj)

    # 아트팩트는 게시 시 doctype/head/body 를 씌워주지만 GitHub Pages 는 파일을
    # 그대로 서빙한다. 껍데기가 없으면 quirks 모드로 뜬다.
    # 템플릿은 <head> 성격(title/link/style) 다음에 <div class="wrap"> 로 본문이
    # 시작하므로 거기서 자른다.
    split = '<div class="wrap">'
    if split not in body:
        raise SystemExit("본문 시작점(%s)을 못 찾았다" % split)
    i = body.index(split)
    head, rest = body[:i], body[i:]
    page = ('<!doctype html>\n<html lang="ko">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="description" content="공릉 실제 보행망 위에서 하는 '
            '원정대 대 쉐도우 추격 게임.">\n'
            + head.strip() + '\n</head>\n<body>\n'
            + rest.strip() + '\n</body>\n</html>\n')

    for out, content in ((OUTS[0], body), (OUTS[1], page)):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        io.open(out, "w", encoding="utf-8").write(content)
        print("  %-24s %6.0f KB" % (os.path.relpath(out, ROOT),
                                    os.path.getsize(out) / 1024.0))

    # 인라인 스크립트 구문 검사.
    # os.system 은 Windows 에서 따옴표 붙은 경로를 cmd 가 다시 벗겨 오작동한다.
    # subprocess 로 인자를 리스트로 넘겨야 공백 있는 경로가 제대로 간다.
    js = re.findall(r"<script>(.*?)</script>", tpl, re.S)
    node = r"C:\Program Files\nodejs\node.exe"
    if js and os.path.exists(node):
        tmp = os.path.join(ROOT, "web", "_syntax_check.js")
        io.open(tmp, "w", encoding="utf-8").write(js[-1])
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
        os.remove(tmp)
        if r.returncode == 0:
            print("  JS 구문 OK")
        else:
            print("  JS 구문 실패:\n" + (r.stderr or "").strip()[:800])
            raise SystemExit(1)


if __name__ == "__main__":
    main()
