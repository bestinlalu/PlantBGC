"""
Tests for src/email_utils.py.

All SMTP connections are mocked — no real emails are sent.
"""
import os
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

import src.email_utils as eu


@pytest.fixture(autouse=True)
def patch_smtp(monkeypatch):
    """Replace smtplib.SMTP with a mock for every test in this module."""
    mock_server = MagicMock()
    mock_smtp_cls = MagicMock(return_value=__import__("contextlib").nullcontext(mock_server))
    monkeypatch.setattr(eu.smtplib, "SMTP", mock_smtp_cls)
    return mock_server


# ── send_email ────────────────────────────────────────────────────────────────

def test_send_email_basic(patch_smtp):
    eu.send_email("to@test.com", "Subject", "Body")
    # Should not raise


def test_send_email_does_not_raise_on_smtp_error(monkeypatch):
    monkeypatch.setattr(eu.smtplib, "SMTP", MagicMock(side_effect=Exception("connection refused")))
    eu.send_email("to@test.com", "Subject", "Body")  # non-fatal


def test_send_email_with_valid_attachment(tmp_path, patch_smtp):
    f = tmp_path / "log.txt"
    f.write_bytes(b"log content")
    eu.send_email("to@test.com", "Subject", "Body", attachments=[str(f)])


def test_send_email_skips_missing_attachment(tmp_path, patch_smtp):
    eu.send_email("to@test.com", "Subject", "Body",
                  attachments=["/nonexistent/file.txt"])
    # Should complete without error


# ── send_queued_email ─────────────────────────────────────────────────────────

def test_send_queued_email_subject_contains_job_name(monkeypatch):
    sent = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, **kw: sent.update(subject=subject, body=body))
    eu.send_queued_email("u@test.com", "MyGenomeRun", 3)
    assert "MyGenomeRun" in sent["subject"]
    assert "3" in sent["body"]


# ── send_started_email ────────────────────────────────────────────────────────

def test_send_started_email_subject_contains_job_name(monkeypatch):
    sent = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, **kw: sent.update(subject=subject))
    eu.send_started_email("u@test.com", "MyGenomeRun")
    assert "MyGenomeRun" in sent["subject"]


# ── send_completion_email ─────────────────────────────────────────────────────

def test_completion_email_complete_contains_download_url(monkeypatch):
    sent = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, **kw: sent.update(body=body))
    job_id = str(uuid.uuid4())
    eu.send_completion_email("u@test.com", "MyRun", "COMPLETE", job_id=job_id)
    assert job_id in sent["body"]
    assert "Download" in sent["body"]


def test_completion_email_failed_contains_error(monkeypatch):
    sent = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, **kw: sent.update(subject=subject, body=body))
    eu.send_completion_email("u@test.com", "MyRun", "FAILED",
                              error_message="OOM killed")
    assert "Failed" in sent["subject"]
    assert "OOM killed" in sent["body"]


# ── send_failure_admin_email ──────────────────────────────────────────────────

def test_failure_admin_email_sent_to_smtp_user(monkeypatch):
    recipients = []
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, **kw: recipients.append(to))
    eu.send_failure_admin_email("MyRun", str(uuid.uuid4()), "u@test.com",
                                 "timeout", None, None)
    assert recipients == [eu.SMTP_USER]


def test_failure_admin_email_attaches_log_and_input(tmp_path, monkeypatch):
    log_file   = tmp_path / "LOG.txt";   log_file.write_bytes(b"log")
    input_file = tmp_path / "genome.fna"; input_file.write_bytes(b">seq\nATCG")

    captured = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, attachments=None, **kw:
                        captured.update(attachments=attachments))

    eu.send_failure_admin_email("MyRun", str(uuid.uuid4()), "u@test.com",
                                 "error", str(log_file), str(input_file))
    assert str(log_file) in captured["attachments"]
    assert str(input_file) in captured["attachments"]


def test_failure_admin_email_skips_missing_files(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(eu, "send_email",
                        lambda to, subject, body, attachments=None, **kw:
                        captured.update(attachments=attachments or []))
    eu.send_failure_admin_email("MyRun", str(uuid.uuid4()), "u@test.com",
                                 "error", "/no/log.txt", "/no/input.fna")
    assert captured["attachments"] == []
