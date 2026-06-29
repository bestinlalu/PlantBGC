from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.database import Base


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    job_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    input_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    input_file_path: Mapped[str] = mapped_column(Text, nullable=False)

    # "genome_dna" | "cds_nucleotide" | "protein_fasta"
    input_type: Mapped[str] = mapped_column(String(50), default="genome_dna")
    # "prepare_only" | "predict_bgc"
    run_mode: Mapped[str] = mapped_column(String(50), default="predict_bgc")

    output_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    allow_training: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
