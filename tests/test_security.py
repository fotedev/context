"""Unit tests for :mod:`gui.server.security`.

Covers the pairing-code + bearer-token lifecycle and the loopback-enforcement
middleware helper.
"""

from __future__ import annotations

import time

import pytest

from gui.server import security


class TestPairingCodeLifecycle:
    def test_generate_then_verify_succeeds(self, reset_security_state) -> None:
        code = security.generate_pairing_code()
        token = security.verify_pairing_code(code)
        assert isinstance(token, str)
        assert len(token) >= 16  # secrets.token_urlsafe(32)

    def test_verify_invalid_code_raises(self, reset_security_state) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            security.verify_pairing_code("never-issued")
        assert exc.value.status_code == 400
        assert "Invalid or expired" in exc.value.detail

    def test_code_single_use(self, reset_security_state) -> None:
        from fastapi import HTTPException

        code = security.generate_pairing_code()
        security.verify_pairing_code(code)  # first use OK
        with pytest.raises(HTTPException):
            security.verify_pairing_code(code)  # second use fails

    def test_expired_code_rejected(self, reset_security_state) -> None:
        from fastapi import HTTPException

        code = security.generate_pairing_code()
        # Backdate the expiry so it looks expired now.
        security._pairing_codes[code] = time.time() - 1
        with pytest.raises(HTTPException):
            security.verify_pairing_code(code)

    def test_revoke_token_invalidates(self, reset_security_state) -> None:
        code = security.generate_pairing_code()
        token = security.verify_pairing_code(code)
        # Token works before revoke.
        assert security._valid_tokens.__contains__(token)
        security.revoke_token(token)
        # After revoke the in-memory set no longer holds it.
        assert not security._valid_tokens.__contains__(token)

    def test_each_pairing_mints_distinct_tokens(self, reset_security_state) -> None:
        codes = [security.generate_pairing_code() for _ in range(3)]
        tokens = [security.verify_pairing_code(c) for c in codes]
        assert len(set(tokens)) == 3  # all unique


class TestEnforceLoopback:
    @pytest.mark.parametrize(
        "host",
        ["127.0.0.1", "::1", "localhost"],
    )
    def test_loopback_hosts_pass(self, reset_security_state, host) -> None:
        # Build a fake Request with a host attribute on .client.
        class _Client:
            pass

        class _Request:
            client = _Client()

        _Request.client.host = host
        security.enforce_loopback(_Request())  # must not raise

    @pytest.mark.parametrize("host", ["10.0.0.1", "192.168.1.1", "evil.example.com"])
    def test_non_loopback_rejected(self, reset_security_state, host) -> None:
        from fastapi import HTTPException

        class _Client:
            pass

        class _Request:
            client = _Client()

        _Request.client.host = host
        with pytest.raises(HTTPException) as exc:
            security.enforce_loopback(_Request())
        assert exc.value.status_code == 403
        assert "non-loopback" in exc.value.detail

    def test_missing_client_rejected(self, reset_security_state) -> None:
        from fastapi import HTTPException

        class _Request:
            client = None

        with pytest.raises(HTTPException):
            security.enforce_loopback(_Request())
