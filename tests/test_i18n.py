"""i18n 카탈로그 검증 (ko/en/jp). 브라우저·앱 기동 불필요."""

from app import i18n, state

STATUSES = ("success", "already", "login_required", "unknown", "error")


def test_all_languages_share_the_same_keys():
    """키 집합이 언어마다 다르면 화면/알림에 키 문자열이 그대로 노출된다."""
    key_sets = {lang: frozenset(i18n.STRINGS[lang]) for lang in i18n.LANGS}
    assert len(set(key_sets.values())) == 1
    assert key_sets["ko"]  # 빈 카탈로그 방지


def test_no_blank_translation():
    for lang in i18n.LANGS:
        for key, value in i18n.STRINGS[lang].items():
            assert value.strip(), f"{lang}:{key}"


def test_status_and_notify_cover_every_status_code():
    for lang in i18n.LANGS:
        for code in STATUSES:
            assert i18n.t(f"status.{code}", lang=lang) != f"status.{code}"
            assert i18n.notify_text(code, lang=lang) != code


def test_notify_text_unknown_status_returns_code():
    """checkin.MESSAGES.get(status, status) 하위호환: 사전에 없으면 코드 그대로."""
    assert i18n.notify_text("weird", lang="en") == "weird"


def test_reason_literals_translate_and_pass_through():
    """스케줄러가 넘기는 한국어 사유는 그 리터럴이 곧 키다. ko는 원문 유지."""
    assert i18n.t("01:23 정기 실행", lang="ko") == "01:23 정기 실행"
    assert i18n.t("01:23 정기 실행", lang="en") == "Daily 01:23 run"
    assert i18n.t("사용자 정의 사유", lang="en") == "사용자 정의 사유"


def test_resolve_lang_aliases_and_unknown():
    assert i18n.resolve_lang("ja") == "jp"
    assert i18n.resolve_lang("JP") == "jp"
    assert i18n.resolve_lang("  ko ") == "ko"
    assert i18n.resolve_lang("de") == "ko"
    assert i18n.resolve_lang(None) == "ko"
    assert i18n.resolve_lang("") == "ko"


def test_t_explicit_lang_and_unknown_key():
    assert i18n.t("ui.save", lang="en") == "Save"
    assert i18n.t("ui.save", lang="jp") == "保存"
    assert i18n.t("no.such.key", lang="en") == "no.such.key"


def test_t_formats_kwargs():
    msg = i18n.t("notify.login_window", lang="en", minutes=10)
    assert "10" in msg
    assert "{minutes}" not in msg


def test_current_lang_follows_settings():
    state.state["settings"]["language"] = "jp"
    assert i18n.current_lang() == "jp"
    assert i18n.t("ui.save") == "保存"


def test_current_lang_defaults_to_ko_when_unset():
    state.state["settings"].pop("language", None)
    assert i18n.current_lang() == i18n.DEFAULT_LANG
    assert i18n.t("ui.save") == "저장"
