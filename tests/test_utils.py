"""Tests for utils.py pure functions — no HTTP/DB required."""
import pytest
from datetime import date
from unittest.mock import patch, MagicMock
from utils import (
    escape_like, parse_date, parse_numeric, parse_integer,
    validate_record_form, validate_ambulatory_form,
)


# ---------------------------------------------------------------------------
# escape_like
# ---------------------------------------------------------------------------

class TestEscapeLike:
    def test_escapes_percent(self):
        assert escape_like('50%') == '50\\%'

    def test_escapes_underscore(self):
        assert escape_like('a_b') == 'a\\_b'

    def test_escapes_backslash(self):
        assert escape_like('a\\b') == 'a\\\\b'

    def test_all_special_chars(self):
        assert escape_like('%_\\') == '\\%\\_\\\\'

    def test_plain_string_unchanged(self):
        assert escape_like('hello world') == 'hello world'

    def test_empty_string(self):
        assert escape_like('') == ''


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_ukrainian_format(self):
        assert parse_date('31.12.2023') == date(2023, 12, 31)

    def test_iso_format(self):
        assert parse_date('2023-12-31') == date(2023, 12, 31)

    def test_both_formats_same_result(self):
        assert parse_date('01.05.2026') == parse_date('2026-05-01')

    def test_invalid_returns_none(self):
        assert parse_date('not-a-date') is None

    def test_empty_returns_none(self):
        assert parse_date('') is None

    def test_none_like_whitespace(self):
        assert parse_date('   ') is None

    def test_custom_default(self):
        assert parse_date('bad', default=date(2000, 1, 1)) == date(2000, 1, 1)


# ---------------------------------------------------------------------------
# parse_numeric
# ---------------------------------------------------------------------------

class TestParseNumeric:
    def test_dot_separator(self):
        assert parse_numeric('123.45') == 123.45

    def test_comma_separator(self):
        assert parse_numeric('123,45') == 123.45

    def test_integer_string(self):
        assert parse_numeric('100') == 100.0

    def test_invalid_returns_none(self):
        assert parse_numeric('abc') is None

    def test_empty_returns_none(self):
        assert parse_numeric('') is None

    def test_zero(self):
        assert parse_numeric('0') == 0.0


# ---------------------------------------------------------------------------
# parse_integer
# ---------------------------------------------------------------------------

class TestParseInteger:
    def test_valid_integer(self):
        assert parse_integer('42') == 42

    def test_invalid_returns_none(self):
        assert parse_integer('abc') is None

    def test_float_string_returns_none(self):
        assert parse_integer('3.5') is None

    def test_empty_returns_none(self):
        assert parse_integer('') is None


# ---------------------------------------------------------------------------
# validate_record_form
# ---------------------------------------------------------------------------

class TestValidateRecordForm:
    def _base_form(self, **overrides):
        data = {
            'date_of_discharge': '2026-05-01',
            'full_name': 'Іванов Іван',
            'treating_physician': 'Лікар',
            'history': '12345',
            'k_days': '5',
        }
        data.update(overrides)
        return data

    def test_valid_form_returns_data(self):
        result, err = validate_record_form(self._base_form())
        assert err is None
        assert result['date_of_discharge'] == date(2026, 5, 1)
        assert result['k_days'] == 5

    def test_missing_required_field(self):
        result, err = validate_record_form(self._base_form(full_name=''))
        assert result is None
        assert err is not None

    def test_death_date_before_discharge_is_error(self):
        data = self._base_form(
            date_of_discharge='2026-05-10',
            date_of_death='2026-05-09',
        )
        result, err = validate_record_form(data)
        assert result is None
        assert 'смерті' in err

    def test_death_date_same_as_discharge_is_ok(self):
        data = self._base_form(
            date_of_discharge='2026-05-10',
            date_of_death='2026-05-10',
        )
        result, err = validate_record_form(data)
        assert err is None

    def test_death_date_after_discharge_is_ok(self):
        data = self._base_form(
            date_of_discharge='2026-05-01',
            date_of_death='2026-05-15',
        )
        result, err = validate_record_form(data)
        assert err is None

    def test_invalid_k_days(self):
        result, err = validate_record_form(self._base_form(k_days='abc'))
        assert result is None
        assert err is not None

    def test_invalid_discharge_date(self):
        result, err = validate_record_form(self._base_form(date_of_discharge='not-a-date'))
        assert result is None
        assert err is not None


# ---------------------------------------------------------------------------
# validate_ambulatory_form
# ---------------------------------------------------------------------------

class TestValidateAmbulatoryForm:
    def _base_form(self, **overrides):
        data = {
            'date': '2026-05-15',
            'journal_number': '100/A',
            'full_name': 'Петров Петро',
            'birth_date': '1990-01-01',
            'doctor': 'Лікар',
            'diagnosis': 'ГРВІ',
        }
        data.update(overrides)
        return data

    def test_valid_form_returns_data(self):
        result, err = validate_ambulatory_form(self._base_form())
        assert err is None
        assert result['full_name'] == 'Петров Петро'

    def test_birth_date_after_visit_date_is_error(self):
        data = self._base_form(date='2026-05-01', birth_date='2026-05-02')
        result, err = validate_ambulatory_form(data)
        assert result is None
        assert 'народження' in err

    def test_birth_date_same_as_visit_is_ok(self):
        data = self._base_form(date='2026-05-01', birth_date='2026-05-01')
        result, err = validate_ambulatory_form(data)
        assert err is None

    def test_missing_required(self):
        result, err = validate_ambulatory_form(self._base_form(doctor=''))
        assert result is None

    def test_invalid_birth_date_format(self):
        result, err = validate_ambulatory_form(self._base_form(birth_date='bad'))
        assert result is None

    def test_is_urgent_flag_on(self):
        result, err = validate_ambulatory_form(self._base_form(is_urgent='on'))
        assert err is None
        assert result['is_urgent'] is True

    def test_is_urgent_flag_off(self):
        result, err = validate_ambulatory_form(self._base_form())
        assert err is None
        assert result['is_urgent'] is False
