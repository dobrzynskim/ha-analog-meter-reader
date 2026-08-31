from analog_meter_reader.validation import parse_ai_response, try_fix_decimal_shift, validate_reading


def test_parse_ai_response_valid_value():
    assert parse_ai_response("515.234") == 515.234


def test_parse_ai_response_strips_whitespace():
    assert parse_ai_response("  515.2 \n") == 515.2


def test_parse_ai_response_uncertain_marker_returns_none():
    assert parse_ai_response("UNCERTAIN") is None


def test_parse_ai_response_garbage_returns_none():
    assert parse_ai_response("nie wiem") is None


def test_parse_ai_response_too_many_decimals_returns_none():
    assert parse_ai_response("515.1234") is None


def test_try_fix_decimal_shift_scales_up():
    # AI zwrocilo 5.153 zamiast 515.3 - brakujacy rzad wielkosci
    assert try_fix_decimal_shift(5.153, last_good=515.2, max_step=2.0) == 515.3


def test_try_fix_decimal_shift_scales_down():
    assert try_fix_decimal_shift(51530.0, last_good=515.2, max_step=2.0) == 515.3


def test_try_fix_decimal_shift_no_match_returns_none():
    assert try_fix_decimal_shift(999.0, last_good=515.2, max_step=2.0) is None


def test_validate_reading_first_run_accepts_anything():
    value, rejected = validate_reading(515.2, last_good=None, max_step=2.0)
    assert (value, rejected) == (515.2, False)


def test_validate_reading_normal_increase_accepted():
    value, rejected = validate_reading(515.4, last_good=515.2, max_step=2.0)
    assert (value, rejected) == (515.4, False)


def test_validate_reading_small_decrease_rejected_keeps_last_good():
    # Rozmazane czerwone cyfry daja czasem pozorny spadek - odrzucamy, nie
    # cofamy licznika.
    value, rejected = validate_reading(515.1, last_good=515.2, max_step=2.0)
    assert (value, rejected) == (515.2, True)


def test_validate_reading_decimal_shift_is_corrected_not_rejected():
    value, rejected = validate_reading(5.153, last_good=515.2, max_step=2.0)
    assert (value, rejected) == (515.3, False)


def test_validate_reading_unrealistic_jump_without_fix_is_rejected():
    value, rejected = validate_reading(999.9, last_good=515.2, max_step=2.0)
    assert (value, rejected) == (515.2, True)


def test_validate_reading_identical_value_is_accepted_not_rejected():
    """Licznik nie musi rosnąć w KAŻDYM cyklu - jeśli w danym oknie nikt nie
    użył wody/gazu, kolejny odczyt będzie identyczny z poprzednim, i to jest
    prawidłowy, nie podejrzany wynik. Warunek odrzucenia to `value <
    last_good` (ostro), nie `value <= last_good`."""
    value, rejected = validate_reading(515.2, last_good=515.2, max_step=2.0)
    assert (value, rejected) == (515.2, False)
