"""사용자에게 보이는 모든 문자열(관리 UI·알림·로그)의 다국어 카탈로그. ko가 기준 언어.

- 키 집합은 세 언어가 완전히 같아야 한다 (`tests/test_i18n.py`가 강제). 빠진 키는
  한국어 → 키 자체 순으로 폴백하므로 화면에 키가 새지는 않지만, 번역 누락은 테스트가 잡는다.
- 스케줄러가 넘기는 실행 사유는 한국어 리터럴이 곧 키다(예: "수동 실행"). 사전에 없으면
  원문이 그대로 나가므로 호출부는 자유로운 문자열을 넘겨도 안전하다.
- 출석 판정 키워드(`checkin.classify_status`)는 SKPORT 페이지 문구지 UI 문구가 아니다. 여기서 다루지 않는다.
"""

from app import state

DEFAULT_LANG = "ko"
LANGS = ("ko", "en", "jp")
LANG_LABELS = {
    "ko": "한국어",
    "en": "English",
    "jp": "日本語",
}  # 선택 목록은 각 언어의 자기 이름으로
HTML_LANG = {
    "ko": "ko",
    "en": "en",
    "jp": "ja",
}  # jp는 내부 코드, HTML lang 속성은 BCP-47
ALIASES = {"ja": "jp", "kr": "ko"}  # 흡수할 별칭
STATUSES = ("success", "already", "login_required", "unknown", "error")

STRINGS = {
    "ko": {
        # 관리 UI
        "ui.title": "SKPORT 에이전트",
        "ui.intro": "매일 01:23 (UTC+8)에만 브라우저를 켜서 출석합니다. 평소에는 브라우저가 꺼져 있습니다.",
        "ui.vnc_link": "VNC로 브라우저 열기",
        "ui.vnc_hint": "(로그인용)",
        "ui.status": "상태",
        "ui.result": "결과",
        "ui.last_run": "마지막 실행",
        "ui.next_run": "다음 실행",
        "ui.session": "저장 세션",
        "ui.session_yes": "있음",
        "ui.session_no": "없음 (로그인 필요)",
        "ui.settings": "설정",
        "ui.language": "언어",
        "ui.notifications": "알림",
        "ui.telegram": "텔레그램 알림",
        "ui.bot_token": "봇 토큰",
        "ui.keep_saved": "비워두면 저장된 값 유지",
        "ui.chat_id": "채널/채팅 ID",
        "ui.chat_id_ph": "예: -1001234567890",
        "ui.mention_id": "멘션할 유저 ID",
        "ui.mention_id_ph": "숫자 ID만 입력 (예: 123456789)",
        "ui.mention_hint": "숫자 ID면 tg://user 보이지 않는 멘션으로 알림이 갑니다.",
        "ui.discord": "디스코드 알림",
        "ui.webhook": "디스코드 웹훅 URL",
        "ui.save": "저장",
        "ui.clear_token": "토큰 지우기",
        "ui.clear_webhook": "웹훅 지우기",
        "ui.saved": "저장됨",
        "ui.not_set": "미설정",
        "ui.run_now": "지금 출석 1회 실행",
        "ui.open_login": "로그인용 브라우저 10분 열기",
        "ui.close_browser": "브라우저 즉시 종료",
        "ui.log": "로그",
        # 상태 코드 라벨
        "status.success": "출석 완료",
        "status.already": "이미 출석됨",
        "status.login_required": "로그인 필요",
        "status.unknown": "결과 불명",
        "status.error": "오류",
        # 알림 문구
        "notify.success": "✅ SKPORT 출석 완료",
        "notify.already": "✅ SKPORT 이미 출석됨 (중복 실행 없음)",
        "notify.login_required": "🚨 SKPORT 로그인 만료 — UI/VNC에서 다시 로그인 필요",
        "notify.unknown": "⚠️ SKPORT 출석 결과 불명 — 로그 확인 필요",
        "notify.error": "❌ SKPORT 출석 실패(네트워크 오류) — 로그 확인 필요",
        "notify.login_window": "🔑 SKPORT 로그인 필요 — {minutes}분간 브라우저를 열어둡니다. 화면/VNC(/vnc.html)로 로그인하세요.",
        # 로그
        "log.agent_started": "에이전트 시작 (FastAPI)",
        "log.settings_changed": "설정 변경: {fields}",
        "log.skip_login_open": "로그인 창이 열려 있어 이번 출석을 건너뜁니다.",
        "log.run_failed": "실행 오류: {error}",
        "log.login_hint": "관리 UI의 '로그인용 브라우저 열기' 버튼 또는 VNC로 로그인하세요.",
        "log.login_window_open_already": "로그인 창이 이미 열려 있습니다.",
        "log.login_window_opening": "{reason}: {minutes}분간 로그인용 브라우저를 엽니다. 화면/VNC(/vnc.html)에서 로그인하세요.",
        "log.login_window_closing": "즉시 종료 요청을 받아 로그인 창을 닫습니다.",
        "log.login_window_closed": "로그인 창을 닫았습니다.",
        "log.login_window_error": "로그인 창 오류: {error}",
        "log.preview_off": "브라우저 꺼짐 (매일 01:23 UTC+8에만 켜짐)",
        # 실행 사유: 한국어는 리터럴이 곧 번역문이다 (다른 언어와 키 집합을 맞추기 위해 자기 자신으로 매핑)
        "수동 실행": "수동 실행",
        "수동 로그인": "수동 로그인",
        "저장 세션 없음": "저장 세션 없음",
        "시작 시 미출석 → 즉시 실행": "시작 시 미출석 → 즉시 실행",
        "01:23 정기 실행": "01:23 정기 실행",
        "세션 만료": "세션 만료",
    },
    "en": {
        # Admin UI
        "ui.title": "SKPORT Agent",
        "ui.intro": "The browser opens once a day at 01:23 (UTC+8) to check in. The rest of the time it stays off.",
        "ui.vnc_link": "Open the browser over VNC",
        "ui.vnc_hint": "(for login)",
        "ui.status": "Status",
        "ui.result": "Result",
        "ui.last_run": "Last run",
        "ui.next_run": "Next run",
        "ui.session": "Saved session",
        "ui.session_yes": "present",
        "ui.session_no": "missing (login required)",
        "ui.settings": "Settings",
        "ui.language": "Language",
        "ui.notifications": "Notifications",
        "ui.telegram": "Telegram notifications",
        "ui.bot_token": "Bot token",
        "ui.keep_saved": "leave empty to keep the saved value",
        "ui.chat_id": "Channel/chat ID",
        "ui.chat_id_ph": "e.g. -1001234567890",
        "ui.mention_id": "User ID to mention",
        "ui.mention_id_ph": "digits only (e.g. 123456789)",
        "ui.mention_hint": "A numeric ID is sent as an invisible tg://user mention.",
        "ui.discord": "Discord notifications",
        "ui.webhook": "Discord webhook URL",
        "ui.save": "Save",
        "ui.clear_token": "Clear token",
        "ui.clear_webhook": "Clear webhook",
        "ui.saved": "saved",
        "ui.not_set": "not set",
        "ui.run_now": "Run check-in once now",
        "ui.open_login": "Open login browser for 10 minutes",
        "ui.close_browser": "Close browser now",
        "ui.log": "Log",
        # Status code labels
        "status.success": "Checked in",
        "status.already": "Already checked in",
        "status.login_required": "Login required",
        "status.unknown": "Unknown result",
        "status.error": "Error",
        # Notifications
        "notify.success": "✅ SKPORT check-in complete",
        "notify.already": "✅ SKPORT already checked in (no duplicate run)",
        "notify.login_required": "🚨 SKPORT session expired — log in again from the UI/VNC",
        "notify.unknown": "⚠️ SKPORT check-in result unknown — check the log",
        "notify.error": "❌ SKPORT check-in failed (network error) — check the log",
        "notify.login_window": "🔑 SKPORT login required — the browser stays open for {minutes} minutes. Log in from the screen or VNC (/vnc.html).",
        # Log
        "log.agent_started": "Agent started (FastAPI)",
        "log.settings_changed": "Settings changed: {fields}",
        "log.skip_login_open": "Skipping this check-in because the login window is open.",
        "log.run_failed": "Run failed: {error}",
        "log.login_hint": "Log in with the 'Open login browser for 10 minutes' button in the admin UI, or over VNC.",
        "log.login_window_open_already": "The login window is already open.",
        "log.login_window_opening": "{reason}: opening the login browser for {minutes} minutes. Log in from the screen or VNC (/vnc.html).",
        "log.login_window_closing": "Close request received — closing the login window now.",
        "log.login_window_closed": "Login window closed.",
        "log.login_window_error": "Login window error: {error}",
        "log.preview_off": "Browser is off (only on at 01:23 UTC+8 daily)",
        # Run reasons (Korean literals used as keys by the scheduler)
        "수동 실행": "Manual run",
        "수동 로그인": "Manual login",
        "저장 세션 없음": "No saved session",
        "시작 시 미출석 → 즉시 실행": "Not checked in at startup → running now",
        "01:23 정기 실행": "Daily 01:23 run",
        "세션 만료": "Session expired",
    },
    "jp": {
        # 管理 UI
        "ui.title": "SKPORT エージェント",
        "ui.intro": "毎日 01:23 (UTC+8) にだけブラウザを起動して出席します。それ以外はブラウザは閉じています。",
        "ui.vnc_link": "VNC でブラウザを開く",
        "ui.vnc_hint": "（ログイン用）",
        "ui.status": "ステータス",
        "ui.result": "結果",
        "ui.last_run": "最終実行",
        "ui.next_run": "次回実行",
        "ui.session": "保存セッション",
        "ui.session_yes": "あり",
        "ui.session_no": "なし（ログインが必要）",
        "ui.settings": "設定",
        "ui.language": "言語",
        "ui.notifications": "通知",
        "ui.telegram": "Telegram 通知",
        "ui.bot_token": "ボットトークン",
        "ui.keep_saved": "空欄なら保存済みの値を維持",
        "ui.chat_id": "チャンネル/チャット ID",
        "ui.chat_id_ph": "例: -1001234567890",
        "ui.mention_id": "メンションするユーザー ID",
        "ui.mention_id_ph": "数字 ID のみ（例: 123456789）",
        "ui.mention_hint": "数値 ID なら tg://user の不可視メンションで通知されます。",
        "ui.discord": "Discord 通知",
        "ui.webhook": "Discord Webhook URL",
        "ui.save": "保存",
        "ui.clear_token": "トークンを削除",
        "ui.clear_webhook": "Webhook を削除",
        "ui.saved": "保存済み",
        "ui.not_set": "未設定",
        "ui.run_now": "今すぐ出席を1回実行",
        "ui.open_login": "ログイン用ブラウザを10分間開く",
        "ui.close_browser": "ブラウザを即時終了",
        "ui.log": "ログ",
        # ステータスコードのラベル
        "status.success": "出席完了",
        "status.already": "出席済み",
        "status.login_required": "ログインが必要",
        "status.unknown": "結果不明",
        "status.error": "エラー",
        # 通知
        "notify.success": "✅ SKPORT 出席完了",
        "notify.already": "✅ SKPORT 出席済み（重複実行なし）",
        "notify.login_required": "🚨 SKPORT ログイン期限切れ — UI/VNC から再ログインが必要",
        "notify.unknown": "⚠️ SKPORT 出席結果不明 — ログを確認してください",
        "notify.error": "❌ SKPORT 出席失敗（ネットワークエラー） — ログを確認してください",
        "notify.login_window": "🔑 SKPORT ログインが必要 — {minutes}分間ブラウザを開きます。画面/VNC（/vnc.html）からログインしてください。",
        # ログ
        "log.agent_started": "エージェント起動 (FastAPI)",
        "log.settings_changed": "設定変更: {fields}",
        "log.skip_login_open": "ログイン画面が開いているため、今回の出席はスキップします。",
        "log.run_failed": "実行エラー: {error}",
        "log.login_hint": "管理 UI の「ログイン用ブラウザを10分間開く」ボタン、または VNC からログインしてください。",
        "log.login_window_open_already": "ログイン画面はすでに開いています。",
        "log.login_window_opening": "{reason}: {minutes}分間ログイン用ブラウザを開きます。画面/VNC（/vnc.html）からログインしてください。",
        "log.login_window_closing": "即時終了の要求を受けたため、ログイン画面を閉じます。",
        "log.login_window_closed": "ログイン画面を閉じました。",
        "log.login_window_error": "ログイン画面エラー: {error}",
        "log.preview_off": "ブラウザは停止中（毎日 01:23 UTC+8 にのみ起動）",
        # 実行理由（スケジューラが渡す韓国語リテラルがキー）
        "수동 실행": "手動実行",
        "수동 로그인": "手動ログイン",
        "저장 세션 없음": "保存セッションなし",
        "시작 시 미출석 → 즉시 실행": "起動時に未出席 → 即時実行",
        "01:23 정기 실행": "01:23 の定期実行",
        "세션 만료": "セッション期限切れ",
    },
}


def resolve_lang(value) -> str:
    """설정값 → 지원 언어 코드. 미지원·비문자열은 ko.

    예외를 던지지 않는 것이 중요하다: Settings 검증에서 raise하면 ValidationError가
    설정 전체를 기본값으로 되돌려 저장된 시크릿까지 날아간다.
    """
    if not isinstance(value, str):
        return DEFAULT_LANG
    code = value.strip().lower()
    return ALIASES.get(code, code) if code in LANGS or code in ALIASES else DEFAULT_LANG


def current_lang() -> str:
    """state에 로드된 설정의 언어 (아직 없으면 ko)."""
    return resolve_lang((state.state.get("settings") or {}).get("language"))


def _lookup(key: str, lang: str):
    for table in (STRINGS.get(lang) or {}, STRINGS[DEFAULT_LANG]):
        if key in table:
            return table[key]
    return None


def t(key: str, lang=None, **fmt) -> str:
    """키 → 현재 언어 문구. 사전에 없으면 한국어 → 키 자체. fmt가 있을 때만 format."""
    text = _lookup(key, lang or current_lang()) or key
    return text.format(**fmt) if fmt else text


def notify_text(status: str, lang=None) -> str:
    """출석 상태 → 알림 문구. 사전에 없는 상태는 코드 그대로 (checkin.MESSAGES.get(status, status) 하위호환)."""
    return _lookup(f"notify.{status}", lang or current_lang()) or status


def status_texts(lang=None) -> dict:
    """관리 UI가 5초 폴링마다 쓰는 상태 코드 → 라벨 맵."""
    lang = lang or current_lang()
    return {code: t(f"status.{code}", lang) for code in STATUSES}
