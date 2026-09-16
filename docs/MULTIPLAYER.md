# 3단계 설계 — 방 코드 · 실시간 동기화 · 채팅

## 원칙 하나

**게임 로직은 한 곳에서만 돈다.** 방장의 브라우저가 심판이고, 나머지는 화면만
그린다. 그래야 6명이 각자 계산하다 결과가 갈리는 일이 없다.

- 참가자가 보내는 것: **의도**뿐 (`내 손은 바위`, `아이템 찬성`, `채팅`)
- 방장이 보내는 것: **확정된 상태** (`3라운드 결과, 쉐도우 승, 다음 노드 812`)
- 참가자는 확정 상태를 받아 그대로 그린다

방장이 나가면 방이 멈춘다. 6명이 같이 노는 규모에서는 이게 제일 단순하고,
"누가 이겼는지" 다툴 일이 없다.

## 데이터 모델 (Firebase Realtime Database)

```
rooms/
  ABCD/                                  방 코드 4자리
    meta/
      host:        "u_a1b2"              방장 uid
      phase:       "lobby"|"pick"|"play"|"done"
      createdAt:   1758...
      mapVersion:  "gongneung-1"         지도 데이터가 바뀌면 올린다
    players/
      u_a1b2: {name:"민수", team:"exp", bot:false, seat:0, online:true}
      b1:     {name:"봇 1", team:"sha", bot:true,  seat:4}
    setup/                               방장만 쓴다. 모두가 실시간으로 본다
      items:    {exp:{re:1,win:0,sk:0}, sha:{re:1,win:0,sk:0}}
      voteRule: "majority"
      limitMin: 60
    game/                                방장만 쓴다
      start: 481                         노드 인덱스
      goal:  612
      cur:   540
      prev:  538
      trail: [481, 495, ...]
      t:     23.4                        경과 분
      ext:   false                       연장권 사용 여부
      junction/                          지금 갈림길 (없으면 null)
        seq:    7                        몇 번째 갈림길인지
        opts:   [541, 602, 588]
        delta:  38.2
        stage:  "declare"|"rps"|"vote"|"dir"
        round:  2
        reveal: {u_a1b2:0, b1:2, ...}    라운드 결과 공개 후에만 채운다
        alive:  [0,1,3,4]
    intents/                             참가자가 쓴다. 방장이 읽고 지운다
      u_a1b2: {kind:"hand", round:2, v:0, at:1758...}
    chat/
      all/  -{key}: {uid, name, text, at}
      exp/  -{key}: {...}                팀 채팅
      sha/  -{key}: {...}
    log/    -{key}: {text, at}           진행 기록
```

### 왜 `intents` 와 `game` 을 나누나

참가자가 `game` 을 직접 쓰면 서로 덮어쓴다. 참가자는 `intents/<내 uid>` 에만
쓰고, 방장이 모아서 `game` 을 갱신한다. 규칙도 그대로 쓸 수 있다 —
`intents/$uid` 는 본인만, `game` 은 방장만.

### 손을 숨기는 방법

가위바위보는 동시에 내야 한다. 그런데 `intents` 를 남이 읽으면 미리 보인다.
규칙으로 **`intents` 는 쓰기만 되고 읽기는 방장만** 가능하게 막는다.
방장이 전원의 손을 모은 뒤에야 `junction/reveal` 에 한꺼번에 공개한다.

```json
{
  "rules": {
    "rooms": {
      "$room": {
        ".read": true,
        "meta":    {".write": "!data.exists() || data.child('host').val() === auth.uid"},
        "players": {"$uid": {".write": "$uid === auth.uid || root.child('rooms/'+$room+'/meta/host').val() === auth.uid"}},
        "setup":   {".write": "root.child('rooms/'+$room+'/meta/host').val() === auth.uid"},
        "game":    {".write": "root.child('rooms/'+$room+'/meta/host').val() === auth.uid"},
        "intents": {
          ".read": "root.child('rooms/'+$room+'/meta/host').val() === auth.uid",
          "$uid": {".read": "$uid === auth.uid", ".write": "$uid === auth.uid"}
        },
        "chat":    {".write": "auth != null"},
        "log":     {".write": "root.child('rooms/'+$room+'/meta/host').val() === auth.uid"}
      }
    }
  }
}
```

익명 로그인(Anonymous Auth)을 쓴다. 계정을 만들 필요가 없고 `auth.uid` 가 생긴다.

## 코드 구조 — 지금 코드를 어떻게 바꾸나

현재는 모든 상태가 전역 `G` 에 있고 함수가 직접 고친다. 그대로 두고 **한 겹만**
끼운다.

```js
var NET = {
  mode: "local",                  // "local" | "host" | "guest"
  send: function(kind, payload){ ... },   // 참가자 -> intents
  push: function(patch){ ... },           // 방장 -> game 갱신 + 브로드캐스트
  on:   function(evt, fn){ ... }          // 상태/채팅 수신
};
```

- **local** — 지금과 똑같이 동작한다. `send` 는 곧바로 로컬 처리, `push` 는 화면 갱신.
- **host** — `push` 가 Firebase 에도 쓴다. `intents` 를 구독해 사람 입력을 받는다.
- **guest** — `send` 가 Firebase 에 쓰고, `game` 구독으로 화면만 갱신한다.

**게임 로직 함수(step/rpsDone/takeDir/move)는 손대지 않는다.** 방장에서만 돌고,
결과가 `NET.push` 로 나간다. 참가자는 그 함수들을 아예 호출하지 않는다.

바꿔야 하는 지점은 세 곳뿐이다:

| 지금 | 3단계 |
|---|---|
| `rpsPrompt()` 가 사람에게 버튼을 보여주고 즉시 처리 | 버튼 → `NET.send("hand", ...)`. 방장이 전원 손을 모으면 진행 |
| `renderLobby()` 가 `PLAYERS` 를 직접 고침 | 방장만 고치고 `players/` 에 쓴다. 모두가 구독해서 다시 그린다 |
| `refresh()` 가 `G` 를 읽어 그림 | 그대로. 다만 guest 의 `G` 는 수신한 스냅샷으로 채운다 |

## 채팅

- **전체** `chat/all` — 로비에서 아이템 분배를 상의할 때
- **팀** `chat/exp`, `chat/sha` — 시작 후 자기 팀만
- 시작 전에는 팀이 바뀔 수 있으므로 **팀 채팅은 시작 후에만** 열린다
- 마지막 50개만 그린다. 오래된 건 방장이 주기적으로 지운다

## 방 만들기 / 들어가기

1. 방장이 `방 만들기` → 4자리 코드 생성(충돌 시 재시도) → `meta/host` 에 자기 uid
2. 참가자는 코드 입력 → `players/<uid>` 에 자기 정보 기록 → 로비 구독
3. 방장이 `시작` → `phase: "play"`, 팀 고정
4. 방장 이탈 시 `online:false` → 남은 사람에게 "방장이 나갔습니다" 표시

## 무료 한도

Realtime Database 무료(Spark): 동시 접속 100, 저장 1 GB, 월 전송 10 GB.
한 판에 오가는 데이터는 수십 KB 수준이라 **한도에 닿을 일이 없다.**

## 아직 정하지 않은 것

- 방장이 나갔을 때 다른 사람에게 넘길지(호스트 이양), 아니면 그냥 끝낼지
- 재접속 처리 — 지금 설계는 새로고침하면 guest 로 다시 붙어 상태를 받는다
- 봇을 방장 브라우저에서 돌리므로, 방장이 느리면 전체가 느려진다
