from __future__ import annotations
import os
import json
from sapmcp.audit import _redact_text, SENSITIVE_KEYS

def test_redact_text_with_file_env(monkeypatch):
    monkeypatch.setenv("SAP_PASS_FILE", "/path/to/secret.txt")

    # Even if we don't have the secret in env, the regex should catch common patterns
    text = "Connecting with password=secret123"
    redacted = _redact_text(text)
    assert "secret123" not in redacted
    assert "password=********" in redacted

def test_redact_text_with_multiple_patterns():
    text = "user: admin, pass: secret, token: 12345"
    redacted = _redact_text(text)
    assert "secret" not in redacted
    assert "12345" not in redacted
    assert "pass=********" in redacted
    assert "token=********" in redacted
