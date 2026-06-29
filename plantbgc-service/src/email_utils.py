"""Shared SMTP email sender — imported by both bgc_web (Python 3.12) and
bgc_worker (Python 3.7), so this module must stay Python 3.7-compatible
(no `str | None`, no walrus in signatures, etc.)."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Optional

from src.config import settings

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "bestinlalu@gmail.com"
SMTP_PASSWORD = "wxpcaezmtnftshrl"


def send_email(to_email: str, subject: str, body: str) -> None:
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"Email dispatched to {to_email}: {subject}")
    except Exception as e:
        print(f"Email send failed (non-fatal): {e}")


def send_queued_email(user_email: str, job_id: str, queue_position: int) -> None:
    subject = f"Analysis Queued — Job #{job_id}"
    body = (
        f"Hello!\n\n"
        f"Your PlantBGC genome analysis (Job {job_id}) has been queued.\n"
        f"Current position in queue: {queue_position}\n\n"
        f"You'll receive another email once processing starts, and again when "
        f"results are ready.\n\n"
        f"Thank you for using PlantBGC."
    )
    send_email(user_email, subject, body)


def send_started_email(user_email: str, job_id: str) -> None:
    subject = f"Analysis Started — Job #{job_id}"
    body = (
        f"Hello!\n\n"
        f"Your PlantBGC genome analysis (Job {job_id}) has started processing.\n\n"
        f"You'll receive another email once your results are ready.\n\n"
        f"Thank you for using PlantBGC."
    )
    send_email(user_email, subject, body)


def send_completion_email(user_email: str, job_id: str, status: str,
                           error_message: Optional[str] = None) -> None:
    download_url = f"{settings.BASE_URL}/api/v1/jobs/{job_id}/download"

    if status == "COMPLETE":
        subject = f"Analysis Complete — Job #{job_id}"
        body = (
            f"Hello!\n\n"
            f"Your PlantBGC genome analysis (Job {job_id}) is complete.\n\n"
            f"Download your results here:\n{download_url}\n\n"
            f"Thank you for using PlantBGC."
        )
    else:
        subject = f"Analysis Failed — Job #{job_id}"
        body = (
            f"Hello,\n\n"
            f"Unfortunately your PlantBGC genome analysis (Job {job_id}) failed.\n"
            f"Error: {error_message or 'Unknown error'}\n\n"
            f"Please try again or contact support."
        )

    send_email(user_email, subject, body)
