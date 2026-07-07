from datetime import date

from scripts import recognition


def test_federal_holidays_2026_key_dates():
    hols = recognition.federal_holidays(2026)
    assert date(2026, 1, 19) in hols      # MLK (3rd Mon Jan)
    assert date(2026, 5, 25) in hols      # Memorial (last Mon May)
    assert date(2026, 9, 7) in hols       # Labor (1st Mon Sep)
    assert date(2026, 11, 26) in hols     # Thanksgiving (4th Thu Nov)
    assert date(2026, 11, 27) in hols     # Friday after Thanksgiving


def test_holiday_weekend_observance():
    # July 4 2026 is a Saturday -> observed Friday July 3.
    hols = recognition.federal_holidays(2026)
    assert date(2026, 7, 3) in hols
    assert date(2026, 7, 4) not in hols


def test_is_attendance_day():
    assert recognition.is_attendance_day(date(2026, 8, 4))    # ordinary Tuesday
    assert not recognition.is_attendance_day(date(2026, 8, 8))  # Saturday
    assert not recognition.is_attendance_day(date(2026, 7, 3))  # observed July 4
    assert not recognition.is_attendance_day(date(2026, 11, 27))  # Black Friday
    assert not recognition.is_attendance_day(date(2026, 12, 28))  # winter break
    assert recognition.is_attendance_day(date(2026, 12, 24))  # Christmas Eve worked


def test_attendance_days_sum_to_150():
    for start in [date(2026, 1, 5), date(2026, 6, 29), date(2026, 8, 3),
                  date(2026, 11, 16), date(2027, 1, 4)]:
        by_year = recognition.attendance_days_by_year(start)
        assert sum(by_year.values()) == 150


def test_cohort_568_two_thirds_one_third_split():
    # Clanton's worked example: 8/3/2026 start earns ~2/3 in 2026, ~1/3 in 2027.
    by_year = recognition.attendance_days_by_year(date(2026, 8, 3))
    assert by_year == {2026: 99, 2027: 51}


def test_january_start_recognized_entirely_in_start_year():
    by_year = recognition.attendance_days_by_year(date(2026, 1, 5))
    assert by_year == {2026: 150}


def test_recognize_splits_amount_proportionally():
    spread = recognition.recognize(date(2026, 8, 3), 300_000)
    assert round(spread[2026]) == 198_000   # 99/150
    assert round(spread[2027]) == 102_000   # 51/150
    assert abs(sum(spread.values()) - 300_000) < 1e-6
