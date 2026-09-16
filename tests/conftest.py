import copy

import pytest

from app import state


@pytest.fixture(autouse=True)
def _isolate_state():
    """모든 테스트가 전역 state를 오염시키지 않도록 스냅샷/복원 (dict 동일성 유지)."""
    saved = copy.deepcopy(state.state)
    yield
    state.state.clear()
    state.state.update(saved)
    state.login_open.clear()
    state.close_requested.clear()
