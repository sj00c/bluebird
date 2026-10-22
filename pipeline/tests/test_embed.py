import pytest

from bluebird.embed import goal_core, text_of


@pytest.mark.parametrize("goal, core", [
    ("공원 내 부족한 조명 문제 개선", "공원 내 부족한 조명"),
    ("어르신 낙상 사고 문제를 해결한다.", "어르신 낙상 사고"),
    ("음식물 곰팡이를 억제하는 천연 방부제가 무엇인지 알아내는 것", "음식물 곰팡이를 억제하는 천연 방부제가 무엇인지"),
    ("동네공원 환경 개선 필요", "동네공원 환경 개선"),
    ("학생들의 안전한 통학환경 조성", "학생들의 안전한 통학환경 조성"),    # 상투어 없음 = 그대로
    ("소음 문제 해결", "소음 문제 해결"),                                  # 떼면 4자 미만 = 안 뗌
])
def test_goal_core_strips_only_trailing_boilerplate(goal, core):
    assert goal_core(goal) == core


def test_text_of_joins_goal_solution_features_and_skips_empty():
    assert text_of("버스 대기시간 문제 해결 ", " 정류장 도착 알림 앱.", ["실시간 위치", " ", "알림"]) == (
        "버스 대기시간. 정류장 도착 알림 앱. 실시간 위치, 알림")
    assert text_of("비누거품 단열 효과를 알아내는 것", "단열 효율 비교 실험", []) == "비누거품 단열 효과를. 단열 효율 비교 실험"
    assert text_of(None, None, None) is None
