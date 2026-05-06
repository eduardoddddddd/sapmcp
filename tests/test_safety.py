import pytest

from sapmcp.config import SafetyPolicy


def test_read_only_allows_known_read_functions():
    policy = SafetyPolicy(read_only=True)
    policy.assert_allowed("RFC_PING")
    policy.assert_allowed("BAPI_USER_GET_DETAIL")


def test_read_only_blocks_unknown_z_function():
    policy = SafetyPolicy(read_only=True)
    with pytest.raises(PermissionError):
        policy.assert_allowed("Z_DO_SOMETHING")


def test_allowlist_allows_z_read_in_read_only():
    policy = SafetyPolicy(read_only=True, allowed_rfc=["Z_SAFE_READ"])
    policy.assert_allowed("Z_SAFE_READ")


def test_allowlist_blocks_non_listed():
    policy = SafetyPolicy(read_only=False, allowed_rfc=["Z_SAFE_READ"])
    with pytest.raises(PermissionError):
        policy.assert_allowed("RFC_PING")


def test_dangerous_requires_double_confirmation():
    policy = SafetyPolicy(read_only=False, allow_dangerous=True)
    with pytest.raises(PermissionError):
        policy.assert_allowed("BAPI_SALESORDER_CREATEFROMDAT2")
    policy.assert_allowed("BAPI_SALESORDER_CREATEFROMDAT2", confirm_dangerous=True)
