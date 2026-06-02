"""Batch Processor - Process entire documents with correction pipeline.

Reads .txt, .md, .rtf files, segments them, processes through the correction
engine, and generates consolidated reports with corrected output files.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .correction_engine import CorrectionApplier, CorrectionPipeline
from .models import Correction, CorrectionReport, CorrectionType, TextStatistics
from .text_segmenter import segment_text

logger = logging.getLogger(__name__)

# Constraints
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
SUPPORTED_EXTENSIONS = {".txt", ".md", ".rtf"}
DEFAULT_SEGMENT_SIZE = 1000  # words
MIN_SEGMENT_SIZE = 100
MAX_SEGMENT_SIZE = 5000


@dataclass
class BatchProgress:
    """Tracks progress of a batch processing job."""

    job_id: str
    total_segments: int
    processed_segments: int = 0
    status: str = "pending"  # pending, processing, completed, failed
    error: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """Get progress as a percentage."""
        if self.total_segments == 0:
            return 0.0
        return round(
            (self.processed_segments / self.total_segments) * 100, 1
        )


@dataclass
class BatchResult:
    """Result of batch processing a file."""

    job_id: str
    input_path: str
    output_path: Optional[str]
    report: Optional[CorrectionReport]
    progress: BatchProgress
    success: bool
    error: Optional[str] = None
    processing_time_ms: float = 0.0


class BatchProcessor:
    """Processes entire documents through the correction pipeline.

    Features:
    - Read .txt, .md, .rtf files up to 10MB.
    - Segment at sentence boundaries (configurable size).
    - Process segments through correction engine.
    - Generate consolidated report.
    - Write corrected output to new file with "-corrected" suffix.
    - Progress tracking.
    """

    def __init__(
        self,
        pipeline: Optional[CorrectionPipeline] = None,
        segment_size: int = DEFAULT_SEGMENT_SIZE,
    ):
        """Initialize the batch processor.

        Args:
            pipeline: The correction pipeline to use.
            segment_size: Number of words per segment.
        """
        self._pipeline = pipeline
        self._segment_size = max(
            MIN_SEGMENT_SIZE, min(MAX_SEGMENT_SIZE, segment_size)
        )
        self._jobs: dict[str, BatchProgress] = {}

    @property
    def segment_size(self) -> int:
        """Current segment size in words."""
        return self._segment_size

    def set_segment_size(self, size: int) -> None:
        """Set the segment size with bounds checking.

        Args:
            size: Desired segment size in words.
        """
        self._segment_size = max(MIN_SEGMENT_SIZE, min(MAX_SEGMENT_SIZE, size))

    def validate_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """Validate a file for batch processing.

        Checks:
        - File exists and is readable.
        - Extension is supported (.txt, .md, .rtf).
        - File size is within limits (10MB).

        Args:
            file_path: Path to the file to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        path = Path(file_path)

        # Check existence
        if not path.exists():
            return False, f"File not found: {file_path}"

        if not path.is_file():
            return False, f"Path is not a file: {file_path}"

        # Check extension
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False, (
                f"Unsupported file format: '{path.suffix}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        # Check file size
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            return False, (
                f"File exceeds maximum size of 10MB "
                f"(actual: {file_size / (1024*1024):.1f}MB)"
            )

        # Check readability
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return False, "File is not valid UTF-8 text"
        except PermissionError:
            return False, f"Permission denied: {file_path}"
        except OSError as e:
            return False, f"Cannot read file: {e}"

        return True, None

    def get_output_path(self, input_path: str) -> str:
        """Generate the output file path with "-corrected" suffix.

        Args:
            input_path: The original input file path.

        Returns:
            Output path with "-corrected" before the extension.
        """
        path = Path(input_path)
        stem = path.stem
        suffix = path.suffix
        return str(path.parent / f"{stem}-corrected{suffix}")

    def read_file(self, file_path: str) -> str:
        """Read a file's content, handling RTF stripping.

        Args:
            file_path: Path to the file.

        Returns:
            The text content of the file.

        Raises:
            ValueError: If the file cannot be read.
        """
        path = Path(file_path)

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ValueError(f"Cannot read file: {e}")

        # Strip RTF formatting if needed
        if path.suffix.lower() == ".rtf":
            content = self._strip_rtf(content)

        return content

    def _strip_rtf(self, content: str) -> str:
        """Strip RTF formatting to get plain text.

        Args:
            content: RTF file content.

        Returns:
            Plain text content.
        """
        try:
            from striprtf.striprtf import rtf_to_text

            return rtf_to_text(content)
        except ImportError:
            # Fallback: basic RTF stripping
            import re

            # Remove RTF control words and groups
            text = re.sub(r"\\[a-z]+\d*\s?", "", content)
            text = re.sub(r"[{}]", "", text)
            text = re.sub(r"\\\'[0-9a-f]{2}", "", text)
            return text.strip()

    async def process_file(
        self,
        file_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[BatchProgress], None]] = None,
    ) -> BatchResult:
        """Process a file through the correction pipeline.

        Args:
            file_path: Path to the input file.
            language: Override language detection.
            progress_callback: Optional callback for progress updates.

        Returns:
            BatchResult with the processing outcome.
        """
        import time

        start_time = time.time()
        job_id = str(uuid.uuid4())

        # Validate file
        is_valid, error = self.validate_file(file_path)
        if not is_valid:
            return BatchResult(
                job_id=job_id,
                input_path=file_path,
                output_path=None,
                report=None,
                progress=BatchProgress(
                    job_id=job_id, total_segments=0, status="failed", error=error
                ),
                success=False,
                error=error,
            )

        # Read file content
        try:
            content = self.read_file(file_path)
        except ValueError as e:
            return BatchResult(
                job_id=job_id,
                input_path=file_path,
                output_path=None,
                report=None,
                progress=BatchProgress(
                    job_id=job_id, total_segments=0, status="failed", error=str(e)
                ),
                success=False,
                error=str(e),
            )

        # Segment the content
        segment_result = segment_text(content, max_words=self._segment_size)

        # Initialize progress
        progress = BatchProgress(
            job_id=job_id,
            total_segments=segment_result.segment_count,
            status="processing",
        )
        self._jobs[job_id] = progress

        if progress_callback:
            progress_callback(progress)

        # Process each segment
        all_corrections: list[Correction] = []

        if self._pipeline:
            for i, segment in enumerate(segment_result.segments):
                try:
                    report = await self._pipeline.analyze(
                        text=segment,
                        language=language,
                    )
                    # Adjust offsets for segment position
                    segment_start = content.find(segment)
                    if segment_start >= 0:
                        for correction in report.corrections:
                            correction.start_offset += segment_start
                            correction.end_offset += segment_start

                    all_corrections.extend(report.corrections)

                except Exception as e:
                    logger.error(f"Error processing segment {i}: {e}")

                progress.processed_segments = i + 1
                if progress_callback:
                    progress_callback(progress)

        # Apply corrections to generate corrected text
        corrected_text = CorrectionApplier.apply_corrections(
            content, all_corrections, mode="all"
        )

        # Write corrected output
        output_path = self.get_output_path(file_path)
        try:
            Path(output_path).write_text(corrected_text, encoding="utf-8")
        except (OSError, PermissionError) as e:
            error_msg = f"Cannot write output file: {e}"
            progress.status = "failed"
            progress.error = error_msg
            return BatchResult(
                job_id=job_id,
                input_path=file_path,
                output_path=None,
                report=None,
                progress=progress,
                success=False,
                error=error_msg,
            )

        # Build consolidated report
        text_stats = TextStatistics(
            word_count=len(content.split()),
            sentence_count=max(
                1, content.count(".") + content.count("!") + content.count("?")
            ),
            character_count=len(content),
            paragraph_count=max(1, content.count("\n\n") + 1),
        )

        consolidated_report = CorrectionReport(
            id=job_id,
            timestamp=datetime.utcnow(),
            original_text=content,
            corrections=all_corrections,
            language_detected=language or "en",
            language_confidence=1.0 if language else 0.0,
            text_statistics=text_stats,
            metadata={
                "input_file": file_path,
                "output_file": output_path,
                "segments_processed": segment_result.segment_count,
                "segment_size": self._segment_size,
            },
        )

        # Update progress
        progress.status = "completed"
        elapsed = (time.time() - start_time) * 1000

        return BatchResult(
            job_id=job_id,
            input_path=file_path,
            output_path=output_path,
            report=consolidated_report,
            progress=progress,
            success=True,
            processing_time_ms=elapsed,
        )

    def get_progress(self, job_id: str) -> Optional[BatchProgress]:
        """Get the progress of a batch job.

        Args:
            job_id: The job identifier.

        Returns:
            BatchProgress if found, None otherwise.
        """
        return self._jobs.get(job_id)
