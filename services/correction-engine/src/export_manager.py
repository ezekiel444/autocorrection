"""Export Manager - Export correction reports in JSON, HTML, and PDF formats.

Provides structured export with summaries including corrections by category,
confidence distribution, and text statistics.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    ConfidenceTier,
    Correction,
    CorrectionReport,
    CorrectionType,
    TextStatistics,
)

logger = logging.getLogger(__name__)

TOOL_VERSION = "0.1.0"


class ExportManager:
    """Exports correction reports in multiple formats.

    Supported formats:
    - JSON: Full structured correction report.
    - HTML: Strikethrough original, underline corrected, summary section.
    - PDF: Header with date/source/version, summary section.

    Summary includes:
    - Corrections by category.
    - Confidence distribution across tiers.
    - Text statistics (word count, sentence count).
    """

    def __init__(self, tool_version: str = TOOL_VERSION):
        """Initialize the export manager.

        Args:
            tool_version: Version string for export headers.
        """
        self._tool_version = tool_version

    def export_json(
        self,
        report: CorrectionReport,
        output_path: Optional[str] = None,
    ) -> str:
        """Export a correction report as JSON.

        Args:
            report: The correction report to export.
            output_path: Optional file path to write to.

        Returns:
            The JSON string.
        """
        data = self._build_export_data(report)
        json_str = json.dumps(data, indent=2, default=str, ensure_ascii=False)

        if output_path:
            self._write_file(output_path, json_str)

        return json_str

    def export_html(
        self,
        report: CorrectionReport,
        output_path: Optional[str] = None,
        source_name: str = "Unknown",
    ) -> str:
        """Export a correction report as HTML.

        Uses strikethrough for original text and underline for corrected text.
        Includes a summary section.

        Args:
            report: The correction report to export.
            output_path: Optional file path to write to.
            source_name: Name of the source document.

        Returns:
            The HTML string.
        """
        summary = self._build_summary(report)
        export_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # Build corrections HTML
        corrections_html = self._build_corrections_html(report.corrections)

        # Build the full HTML document
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Correction Report - {source_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        .header h1 {{
            color: #2E7D32;
            margin-bottom: 0.5rem;
        }}
        .meta {{
            color: #666;
            font-size: 0.9rem;
        }}
        .summary {{
            background: #f5f5f5;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .summary h2 {{
            margin-top: 0;
            color: #1976D2;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .stat-card {{
            background: white;
            border-radius: 4px;
            padding: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .stat-card .label {{
            font-size: 0.85rem;
            color: #666;
            text-transform: uppercase;
        }}
        .stat-card .value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #333;
        }}
        .corrections {{
            margin-top: 2rem;
        }}
        .correction-item {{
            border-left: 4px solid #FFC107;
            padding: 1rem;
            margin-bottom: 1rem;
            background: #FFFDE7;
            border-radius: 0 4px 4px 0;
        }}
        .correction-item.severity-error {{
            border-left-color: #F44336;
            background: #FFEBEE;
        }}
        .correction-item.severity-suggestion {{
            border-left-color: #2196F3;
            background: #E3F2FD;
        }}
        .original {{
            text-decoration: line-through;
            color: #D32F2F;
        }}
        .corrected {{
            text-decoration: underline;
            color: #388E3C;
            font-weight: 500;
        }}
        .correction-meta {{
            font-size: 0.85rem;
            color: #666;
            margin-top: 0.5rem;
        }}
        .confidence-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
        }}
        .confidence-high {{ background: #C8E6C9; color: #2E7D32; }}
        .confidence-medium {{ background: #FFF9C4; color: #F57F17; }}
        .confidence-low {{ background: #FFCDD2; color: #C62828; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Correction Report</h1>
        <div class="meta">
            <p>Source: {source_name} | Date: {export_date} | Tool Version: {self._tool_version}</p>
            <p>Language: {report.language_detected} (confidence: {report.language_confidence:.0%})</p>
        </div>
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Corrections</div>
                <div class="value">{summary['total_corrections']}</div>
            </div>
            <div class="stat-card">
                <div class="label">Word Count</div>
                <div class="value">{summary['text_statistics']['word_count']}</div>
            </div>
            <div class="stat-card">
                <div class="label">Sentence Count</div>
                <div class="value">{summary['text_statistics']['sentence_count']}</div>
            </div>
            <div class="stat-card">
                <div class="label">High Confidence</div>
                <div class="value">{summary['confidence_distribution']['high']}</div>
            </div>
        </div>

        <h3>Corrections by Category</h3>
        <ul>
"""

        for category, count in summary["corrections_by_category"].items():
            html += f"            <li><strong>{category}</strong>: {count}</li>\n"

        html += """        </ul>

        <h3>Confidence Distribution</h3>
        <ul>
"""

        for tier, count in summary["confidence_distribution"].items():
            html += f"            <li><strong>{tier.capitalize()}</strong>: {count}</li>\n"

        html += f"""        </ul>
    </div>

    <div class="corrections">
        <h2>Corrections ({len(report.corrections)})</h2>
{corrections_html}
    </div>
</body>
</html>"""

        if output_path:
            self._write_file(output_path, html)

        return html

    def export_pdf(
        self,
        report: CorrectionReport,
        output_path: str,
        source_name: str = "Unknown",
    ) -> bool:
        """Export a correction report as PDF.

        Includes header with date, source, and version. Uses reportlab
        if available, falls back to HTML-to-PDF conversion.

        Args:
            report: The correction report to export.
            output_path: File path to write the PDF to.
            source_name: Name of the source document.

        Returns:
            True if export was successful.
        """
        try:
            return self._export_pdf_reportlab(report, output_path, source_name)
        except ImportError:
            logger.info("reportlab not available, trying weasyprint")
            try:
                return self._export_pdf_weasyprint(report, output_path, source_name)
            except ImportError:
                logger.warning(
                    "Neither reportlab nor weasyprint available. "
                    "Falling back to HTML export."
                )
                # Fallback: save as HTML
                html_path = output_path.replace(".pdf", ".html")
                self.export_html(report, html_path, source_name)
                return False

    def _export_pdf_reportlab(
        self,
        report: CorrectionReport,
        output_path: str,
        source_name: str,
    ) -> bool:
        """Export PDF using reportlab.

        Args:
            report: The correction report.
            output_path: Output file path.
            source_name: Source document name.

        Returns:
            True if successful.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        summary = self._build_summary(report)
        export_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        doc = SimpleDocTemplate(output_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Header
        header_style = ParagraphStyle(
            "Header",
            parent=styles["Heading1"],
            textColor=colors.HexColor("#2E7D32"),
        )
        elements.append(Paragraph("Correction Report", header_style))
        elements.append(Spacer(1, 0.5 * cm))

        # Metadata
        meta_style = ParagraphStyle(
            "Meta", parent=styles["Normal"], textColor=colors.grey
        )
        elements.append(
            Paragraph(f"Source: {source_name}", meta_style)
        )
        elements.append(
            Paragraph(f"Date: {export_date}", meta_style)
        )
        elements.append(
            Paragraph(f"Tool Version: {self._tool_version}", meta_style)
        )
        elements.append(
            Paragraph(
                f"Language: {report.language_detected} "
                f"(confidence: {report.language_confidence:.0%})",
                meta_style,
            )
        )
        elements.append(Spacer(1, 1 * cm))

        # Summary section
        elements.append(Paragraph("Summary", styles["Heading2"]))
        elements.append(Spacer(1, 0.3 * cm))

        # Summary table
        summary_data = [
            ["Metric", "Value"],
            ["Total Corrections", str(summary["total_corrections"])],
            ["Word Count", str(summary["text_statistics"]["word_count"])],
            ["Sentence Count", str(summary["text_statistics"]["sentence_count"])],
            ["Character Count", str(summary["text_statistics"]["character_count"])],
        ]

        summary_table = Table(summary_data, colWidths=[8 * cm, 6 * cm])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4CAF50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 0.5 * cm))

        # Corrections by category
        elements.append(Paragraph("Corrections by Category", styles["Heading3"]))
        for category, count in summary["corrections_by_category"].items():
            elements.append(
                Paragraph(f"• {category}: {count}", styles["Normal"])
            )
        elements.append(Spacer(1, 0.3 * cm))

        # Confidence distribution
        elements.append(Paragraph("Confidence Distribution", styles["Heading3"]))
        for tier, count in summary["confidence_distribution"].items():
            elements.append(
                Paragraph(f"• {tier.capitalize()}: {count}", styles["Normal"])
            )
        elements.append(Spacer(1, 1 * cm))

        # Corrections list
        elements.append(Paragraph("Corrections", styles["Heading2"]))
        elements.append(Spacer(1, 0.3 * cm))

        for i, correction in enumerate(report.corrections[:200], 1):
            correction_text = (
                f"<b>{i}.</b> "
                f"<strike>{correction.original_text}</strike> → "
                f"<u>{correction.suggested_text}</u><br/>"
                f"<font size='8' color='grey'>"
                f"Type: {correction.correction_type.value} | "
                f"Confidence: {correction.confidence:.0%} | "
                f"Severity: {correction.severity.value}"
                f"</font>"
            )
            elements.append(Paragraph(correction_text, styles["Normal"]))
            elements.append(Spacer(1, 0.2 * cm))

        # Build PDF
        doc.build(elements)
        return True

    def _export_pdf_weasyprint(
        self,
        report: CorrectionReport,
        output_path: str,
        source_name: str,
    ) -> bool:
        """Export PDF using weasyprint (HTML to PDF).

        Args:
            report: The correction report.
            output_path: Output file path.
            source_name: Source document name.

        Returns:
            True if successful.
        """
        from weasyprint import HTML

        html_content = self.export_html(report, source_name=source_name)
        HTML(string=html_content).write_pdf(output_path)
        return True

    def _build_export_data(self, report: CorrectionReport) -> dict:
        """Build the full export data structure.

        Args:
            report: The correction report.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        summary = self._build_summary(report)

        corrections_data = []
        for c in report.corrections:
            corrections_data.append(
                {
                    "original_text": c.original_text,
                    "suggested_text": c.suggested_text,
                    "correction_type": c.correction_type.value,
                    "confidence": c.confidence,
                    "confidence_tier": c.confidence_tier.value,
                    "reason": c.reason,
                    "start_offset": c.start_offset,
                    "end_offset": c.end_offset,
                    "severity": c.severity.value,
                    "rule_name": c.rule_name,
                    "is_overridden": c.is_overridden,
                    "source": c.source,
                }
            )

        return {
            "report_id": report.id,
            "timestamp": report.timestamp.isoformat(),
            "tool_version": self._tool_version,
            "language_detected": report.language_detected,
            "language_confidence": report.language_confidence,
            "original_text": report.original_text,
            "corrections": corrections_data,
            "summary": summary,
            "metadata": report.metadata,
        }

    def _build_summary(self, report: CorrectionReport) -> dict:
        """Build the summary section for exports.

        Args:
            report: The correction report.

        Returns:
            Summary dictionary.
        """
        # Corrections by category
        by_category: dict[str, int] = {}
        for c in report.corrections:
            cat = c.correction_type.value
            by_category[cat] = by_category.get(cat, 0) + 1

        # Confidence distribution
        distribution = report.confidence_distribution()
        confidence_dist = {
            tier.value: count for tier, count in distribution.items()
        }

        return {
            "total_corrections": len(report.corrections),
            "corrections_by_category": by_category,
            "confidence_distribution": confidence_dist,
            "text_statistics": {
                "word_count": report.text_statistics.word_count,
                "sentence_count": report.text_statistics.sentence_count,
                "character_count": report.text_statistics.character_count,
                "paragraph_count": report.text_statistics.paragraph_count,
            },
        }

    def _build_corrections_html(self, corrections: list[Correction]) -> str:
        """Build HTML for the corrections list.

        Args:
            corrections: List of corrections.

        Returns:
            HTML string for the corrections section.
        """
        html_parts = []

        for correction in corrections:
            severity_class = f"severity-{correction.severity.value}"
            confidence_tier = correction.confidence_tier.value
            confidence_class = f"confidence-{confidence_tier}"

            html_parts.append(f"""        <div class="correction-item {severity_class}">
            <p>
                <span class="original">{self._escape_html(correction.original_text)}</span>
                →
                <span class="corrected">{self._escape_html(correction.suggested_text)}</span>
            </p>
            <div class="correction-meta">
                <span class="confidence-badge {confidence_class}">
                    {correction.confidence:.0%}
                </span>
                | Type: {correction.correction_type.value}
                | Severity: {correction.severity.value}
                {f'| Rule: {correction.rule_name}' if correction.rule_name else ''}
            </div>
            <p><em>{self._escape_html(correction.reason)}</em></p>
        </div>""")

        return "\n".join(html_parts)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters.

        Args:
            text: Text to escape.

        Returns:
            HTML-safe text.
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

    @staticmethod
    def _write_file(path: str, content: str) -> None:
        """Write content to a file.

        Args:
            path: File path.
            content: Content to write.

        Raises:
            OSError: If the file cannot be written.
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
