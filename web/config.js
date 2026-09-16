/* 사이트 설정 — 이 파일만 고치면 재빌드 없이 키를 바꿀 수 있다.
 *
 * kakaoKey 는 카카오 **JavaScript 키**다. 웹페이지 소스에 그대로 실리는 공개
 * 식별자이고, 보안은 카카오 콘솔의 도메인 제한(JavaScript SDK 도메인)으로 건다.
 * 그래서 공개 저장소에 있어도 남이 다른 도메인에서 쓸 수 없다.
 * ※ REST API 키와 Admin 키는 진짜 비밀이므로 여기 절대 넣지 말 것.
 */
window.RSP_CONFIG = {
  kakaoKey: "0af0ebee6df4a9d5da671af7af7139db",

  /* 3단계에서 채운다. Firebase 웹 설정도 공개 클라이언트 값이며
     보안은 Realtime Database 규칙으로 건다. docs/MULTIPLAYER.md 참조. */
  firebase: null
};
