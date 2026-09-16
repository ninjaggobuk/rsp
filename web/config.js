/* 사이트 설정 — 이 파일만 고치면 재빌드 없이 키를 바꿀 수 있다.
 *
 * 둘 다 웹페이지 소스에 그대로 실리는 **공개 클라이언트 식별자**다.
 *   kakaoKey  : 보안은 카카오 콘솔의 도메인 제한(JavaScript SDK 도메인)으로 건다.
 *   firebase  : 보안은 Realtime Database 규칙으로 건다 (docs/database.rules.json).
 * REST API 키, Admin 키, 서비스 계정 키는 진짜 비밀이므로 여기 절대 넣지 말 것.
 */
window.RSP_CONFIG = {
  kakaoKey: "0af0ebee6df4a9d5da671af7af7139db",

  firebase: {
    apiKey: "AIzaSyBc0M-sqS19QUy0FECkn48qWMti6r8jNEo",
    authDomain: "rsp-project-e9fcb.firebaseapp.com",
    databaseURL: "https://rsp-project-e9fcb-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "rsp-project-e9fcb",
    storageBucket: "rsp-project-e9fcb.firebasestorage.app",
    messagingSenderId: "134630863590",
    appId: "1:134630863590:web:5c567438f1adc3371e0127"
  }
};
