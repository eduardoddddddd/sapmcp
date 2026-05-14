from __future__ import annotations
import os
import pytest
from pathlib import Path
from sapmcp.config import SapConnectionConfig, DEFAULT_DESTINATION_NAME

def test_password_from_file(monkeypatch, tmp_path):
    password_file = tmp_path / "sap_pass.txt"
    password_file.write_text("FILE_SECRET_789", encoding="utf-8")

    monkeypatch.setenv("SAP_USER", "FILEUSER")
    monkeypatch.setenv("SAP_PASS_FILE", str(password_file))
    monkeypatch.setenv("SAP_ASHOST", "host")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")

    config = SapConnectionConfig.from_destination(DEFAULT_DESTINATION_NAME)
    assert config.params["PASSWD"] == "FILE_SECRET_789"

def test_password_file_priority_over_env(monkeypatch, tmp_path):
    password_file = tmp_path / "sap_pass.txt"
    password_file.write_text("FILE_PRIORITY", encoding="utf-8")

    monkeypatch.setenv("SAP_USER", "PRIORITYUSER")
    monkeypatch.setenv("SAP_PASS_FILE", str(password_file))
    monkeypatch.setenv("SAP_PASS", "ENV_SECRET")
    monkeypatch.setenv("SAP_ASHOST", "host")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")

    config = SapConnectionConfig.from_destination(DEFAULT_DESTINATION_NAME)
    assert config.params["PASSWD"] == "FILE_PRIORITY"

def test_named_destination_password_from_file(monkeypatch, tmp_path):
    password_file = tmp_path / "dev_pass.txt"
    password_file.write_text("DEV_FILE_SECRET", encoding="utf-8")

    monkeypatch.setenv("SAPMCP_DESTINATIONS", "DEV")
    monkeypatch.setenv("SAP_DEV_USER", "DEVUSER")
    monkeypatch.setenv("SAP_DEV_PASS_FILE", str(password_file))
    monkeypatch.setenv("SAP_DEV_ASHOST", "devhost")
    monkeypatch.setenv("SAP_DEV_SYSNR", "01")
    monkeypatch.setenv("SAP_DEV_CLIENT", "110")

    config = SapConnectionConfig.from_destination("DEV")
    assert config.params["PASSWD"] == "DEV_FILE_SECRET"

def test_invalid_password_file_falls_back_to_env(monkeypatch, tmp_path):
    non_existent = tmp_path / "missing.txt"

    monkeypatch.setenv("SAP_USER", "FALLBACKUSER")
    monkeypatch.setenv("SAP_PASS_FILE", str(non_existent))
    monkeypatch.setenv("SAP_PASS", "FALLBACK_SECRET")
    monkeypatch.setenv("SAP_ASHOST", "host")
    monkeypatch.setenv("SAP_SYSNR", "00")
    monkeypatch.setenv("SAP_CLIENT", "100")

    config = SapConnectionConfig.from_destination(DEFAULT_DESTINATION_NAME)
    assert config.params["PASSWD"] == "FALLBACK_SECRET"
