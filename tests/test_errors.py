"""Tests for error hierarchy."""

import pytest

from src.errors import BaseError, DataAccessError, NotFoundError, ProcessingError, ValidationError


class TestBaseError:
    def test_init_minimal_creates_error_with_code_and_message(self):
        err = BaseError(code="TEST_ERR", message="something broke")
        assert err.code == "TEST_ERR"
        assert err.message == "something broke"
        assert err.context == {}
        assert err.cause is None

    def test_init_full_creates_error_with_all_fields(self):
        cause = ValueError("root cause")
        err = BaseError(
            code="TEST_ERR",
            message="something broke",
            context={"file": "test.proto"},
            cause=cause,
        )
        assert err.code == "TEST_ERR"
        assert err.context == {"file": "test.proto"}
        assert err.cause is cause

    def test_str_includes_code_and_message(self):
        err = BaseError(code="TEST_ERR", message="broke")
        assert "[TEST_ERR]" in str(err)
        assert "broke" in str(err)

    def test_str_includes_context_when_present(self):
        err = BaseError(code="X", message="y", context={"k": "v"})
        assert "context=" in str(err)

    def test_str_includes_cause_when_present(self):
        err = BaseError(code="X", message="y", cause=ValueError("z"))
        assert "cause=" in str(err)


class TestErrorHierarchy:
    @pytest.mark.parametrize("cls", [ValidationError, NotFoundError, DataAccessError, ProcessingError])
    def test_subclass_inherits_base_error(self, cls):
        err = cls(code="CODE", message="msg")
        assert isinstance(err, BaseError)
        assert isinstance(err, Exception)

    @pytest.mark.parametrize("cls", [ValidationError, NotFoundError, DataAccessError, ProcessingError])
    def test_subclass_carries_all_fields(self, cls):
        cause = RuntimeError("root")
        err = cls(code="CODE", message="msg", context={"a": 1}, cause=cause)
        assert err.code == "CODE"
        assert err.message == "msg"
        assert err.context == {"a": 1}
        assert err.cause is cause
