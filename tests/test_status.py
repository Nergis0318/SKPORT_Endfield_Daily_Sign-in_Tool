from checkin import classify_status


def test_already_ko():
    assert classify_status("이미 출석하셨습니다") == "already"


def test_already_en():
    assert classify_status("You have already checked in today") == "already"


def test_success_ko():
    assert classify_status("출석 완료! 보상을 수령하세요") == "success"


def test_success_en():
    assert classify_status("Checked in successfully") == "success"


def test_login_required():
    assert classify_status("로그인이 필요합니다") == "login_required"


def test_unknown():
    assert classify_status("Welcome to the SKPORT community") == "unknown"
