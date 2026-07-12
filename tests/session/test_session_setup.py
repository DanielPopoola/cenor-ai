from session.session_setup import build_default_segments


def test_produces_4_segments_covering_all_prd_areas():
    specs = build_default_segments(30)
    assert len(specs) == 4
    assert {s.area for s in specs} == {
        "programming_algorithms", "frameworks_tools", "specialized", "system_design",
    }


def test_only_programming_algorithms_has_editor_available():
    specs = build_default_segments(30)
    editor_areas = {s.area for s in specs if s.editor_available}
    assert editor_areas == {"programming_algorithms"}


def test_durations_sum_exactly_to_session_total_evenly_divisible():
    specs = build_default_segments(40)
    assert sum(s.duration_limit_minutes for s in specs) == 40


def test_durations_sum_exactly_to_session_total_with_remainder():
    specs = build_default_segments(30)  # 30 / 4 = 7 remainder 2
    assert sum(s.duration_limit_minutes for s in specs) == 30


def test_remainder_minutes_go_to_last_segment():
    specs = build_default_segments(30)
    base = 30 // 4
    for spec in specs[:-1]:
        assert spec.duration_limit_minutes == base
    assert specs[-1].duration_limit_minutes == base + (30 - base * 4)


def test_segment_order_matches_list_order():
    specs = build_default_segments(30)
    assert specs[0].area == "programming_algorithms"
    assert specs[-1].area == "system_design"
