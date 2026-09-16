# -*- coding: utf-8 -*-
"""Windows conda env 의 DLL 검색 경로를 스스로 채운다.

왜 필요한가: `envs/rsp/python.exe` 를 activate 없이 직접 호출하면 PATH 에
env 의 `Library/bin` 이 없다. 순수 파이썬 import 는 멀쩡히 되지만, matplotlib 의
Agg 백엔드가 **그리는 시점에** 지연로드(delay-load)하는 네이티브 DLL 을 못 찾아
`0xc06d007f` 로 프로세스가 통째로 죽는다 — 파이썬 예외가 아니라서 traceback 도
안 남고, 파이프 버퍼에 있던 출력까지 같이 날아간다. (2026-09-16 에 이걸로
`savefig` 가 조용히 죽었다.)

Windows 는 LoadLibrary 때 PATH 를 매번 읽으므로, import 전에 `os.environ["PATH"]`
앞에 끼워 넣으면 해결된다. `os.add_dll_directory` 도 같이 걸어둔다.

★ matplotlib / osmnx 를 import 하기 **전에** 호출해야 한다.
"""
import os
import sys

# conda activate 가 PATH 앞에 붙이는 디렉터리들과 같은 순서.
_SUBDIRS = ["", "Library/mingw-w64/bin", "Library/usr/bin", "Library/bin",
            "Scripts", "bin"]

_done = False


def ensure_conda_dll_path():
    """env 의 DLL 디렉터리를 PATH 앞에 붙인다. 두 번 불러도 안전하다."""
    global _done
    if _done:
        return []
    root = os.path.dirname(os.path.abspath(sys.executable))
    dirs = [os.path.normpath(os.path.join(root, s)) for s in _SUBDIRS]
    dirs = [d for d in dirs if os.path.isdir(d)]

    cur = os.environ.get("PATH", "")
    have = set(p.lower().rstrip("\\/") for p in cur.split(os.pathsep))
    add = [d for d in dirs if d.lower().rstrip("\\/") not in have]
    if add:
        os.environ["PATH"] = os.pathsep.join(add + [cur])

    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass          # 비-Windows 이거나 이미 등록됨 — 무해하다

    _done = True
    return add
