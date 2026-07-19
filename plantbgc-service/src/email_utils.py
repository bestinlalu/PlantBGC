"""Shared SMTP email sender — imported by both bgc_web (Python 3.12) and
bgc_worker (Python 3.7), so this module must stay Python 3.7-compatible
(no `str | None`, no walrus in signatures, etc.)."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional

from src.config import settings
from src.logging_config import logger

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]


def send_email(to_email: str, subject: str, body: str,
               attachments: Optional[List[str]] = None) -> None:
    try:
        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body))
            for path in attachments:
                if not os.path.isfile(path):
                    continue
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={os.path.basename(path)}"
                )
                msg.attach(part)
        else:
            msg = MIMEText(body)

        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email dispatched to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Email send failed (non-fatal): {e}")


def send_queued_email(user_email: str, job_name: str, queue_position: int) -> None:
    subject = f"Analysis Queued — {job_name}"
    body = (
        f"Hello!\n\n"
        f"Your PlantBGC genome analysis \"{job_name}\" has been queued.\n"
        f"Current position in queue: {queue_position}\n\n"
        f"You'll receive another email once processing starts, and again when "
        f"results are ready.\n\n"
        f"Thank you for using PlantBGC."
    )
    send_email(user_email, subject, body)


def send_started_email(user_email: str, job_name: str) -> None:
    subject = f"Analysis Started — {job_name}"
    body = (
        f"Hello!\n\n"
        f"Your PlantBGC genome analysis \"{job_name}\" has started processing.\n\n"
        f"You'll receive another email once your results are ready.\n\n"
        f"Thank you for using PlantBGC."
    )
    send_email(user_email, subject, body)


def send_failure_admin_email(job_name: str, job_id: str, user_email: str,
                              error_message: Optional[str],
                              log_path: Optional[str],
                              input_file_path: Optional[str]) -> None:
    subject = f"[PlantBGC] Job Failed — {job_name}"
    body = (
        f"A PlantBGC job has failed.\n\n"
        f"Job Name  : {job_name}\n"
        f"Job ID    : {job_id}\n"
        f"Submitted by: {user_email}\n\n"
        f"Error:\n{error_message or 'Unknown error'}\n\n"
        f"Log and input file are attached."
    )
    attachments = [p for p in [log_path, input_file_path] if p and os.path.isfile(p)]
    send_email(SMTP_USER, subject, body, attachments=attachments)


def send_completion_email(user_email: str, job_name: str, status: str,
                           error_message: Optional[str] = None,
                           job_id: Optional[str] = None) -> None:
    download_url = f"{settings.BASE_URL}/api/v1/jobs/{job_id}/download" if job_id else None

    if status == "COMPLETE":
        subject = f"Analysis Complete — {job_name}"
        body = (
            f"Hello!\n\n"
            f"Your PlantBGC genome analysis \"{job_name}\" is complete.\n\n"
            f"Download your results here:\n{download_url}\n\n"
            f"Thank you for using PlantBGC."
        )
    else:
        subject = f"Analysis Failed — {job_name}"
        body = (
            f"Hello,\n\n"
            f"Unfortunately your PlantBGC genome analysis \"{job_name}\" failed.\n"
            f"Error: {error_message or 'Unknown error'}\n\n"
            f"Please try again or contact support."
        )

    send_email(user_email, subject, body)