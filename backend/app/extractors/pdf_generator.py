import os
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple, TypedDict
import fitz

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
WIDTH = 595.2   # A4 width in points
HEIGHT = 841.8  # A4 height in points
MARGIN = 54.0   # 0.75 in margins
LINE_HEIGHT = 14.0

class Colors:
    BRAND_DARK  = (0.1,  0.1,  0.35)
    BRAND_MID   = (0.15, 0.15, 0.4)
    MUTED       = (0.5,  0.5,  0.5)
    RISK_BG     = (0.95, 0.95, 0.98)
    TEXT_COLOR  = (0.15, 0.15, 0.15)

RISK_COLORS: Dict[str, Tuple[float, float, float]] = {
    "CRITICAL": (0.55, 0.0, 0.0),
    "HIGH":     (0.7, 0.1, 0.1),
    "MEDIUM":   (0.75, 0.45, 0.0),
    "LOW":      (0.4, 0.4, 0.4),
}

class ExtractedEntities(TypedDict, total=False):
    parties: List[str]
    obligations: List[str]
    amounts: List[str]
    dates: List[str]

# ── Font Loading ──────────────────────────────────────────────────────────────
def find_font(paths: List[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None

HINDI_FONT_REGULAR = find_font([
    "C:/Windows/Fonts/Nirmala.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
])

HINDI_FONT_BOLD = find_font([
    "C:/Windows/Fonts/Nirmala.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
])

# ── PDF Layout Engine ─────────────────────────────────────────────────────────
class PDFDocument:
    def __init__(self, doc: fitz.Document):
        self.doc = doc
        self.page = None
        self.y = MARGIN
        self.max_width = WIDTH - 2 * MARGIN
        self.section_counter = 0

        # Load font objects for text length measurements
        self.font_reg = fitz.Font(fontfile=HINDI_FONT_REGULAR) if HINDI_FONT_REGULAR else fitz.Font(fontname="helv")
        self.font_bold = fitz.Font(fontfile=HINDI_FONT_BOLD) if HINDI_FONT_BOLD else fitz.Font(fontname="helv-bold")
        
        # Add the first page
        self.add_page()

    def add_page(self):
        self.page = self.doc.new_page(width=WIDTH, height=HEIGHT)
        
        # Embed Hindi/Devanagari fonts on the page if available
        if HINDI_FONT_REGULAR:
            self.page.insert_font(fontname="Nirmala", fontfile=HINDI_FONT_REGULAR)
        if HINDI_FONT_BOLD:
            self.page.insert_font(fontname="Nirmala-Bold", fontfile=HINDI_FONT_BOLD)

        # Draw header banner line
        self.page.draw_rect(
            fitz.Rect(MARGIN, MARGIN - 15, WIDTH - MARGIN, MARGIN - 13),
            color=(0.8, 0.8, 0.8),
            fill=None,
            width=1
        )
        self.page.insert_text(
            fitz.Point(MARGIN, MARGIN - 20),
            "DocMind AI Analysis Report",
            fontname="Helvetica",
            fontsize=8,
            color=Colors.MUTED
        )
        self.page.insert_text(
            fitz.Point(WIDTH - MARGIN - 50, MARGIN - 20),
            f"Page {self.doc.page_count}",
            fontname="Helvetica",
            fontsize=8,
            color=Colors.MUTED
        )
        self.y = MARGIN + 15

    def get_font_params(self, fontname: str) -> Tuple[str, fitz.Font]:
        """Returns the registered font name and the Font measurement object."""
        is_bold = "bold" in fontname.lower()
        if is_bold:
            if HINDI_FONT_BOLD:
                return "Nirmala-Bold", self.font_bold
            return fontname, self.font_bold
        else:
            if HINDI_FONT_REGULAR:
                return "Nirmala", self.font_reg
            return fontname, self.font_reg

    def write_paragraph(
        self,
        text: str,
        fontname="Helvetica",
        fontsize=9.5,
        color=Colors.TEXT_COLOR,
        spacing=6.0
    ) -> float:
        registered_name, font_obj = self.get_font_params(fontname)

        # H1: Split Unicode text, normalize ZWS characters, and split on whitespace/newlines
        text = text.replace('\u200b', ' ').replace('\u200c', '').replace('\u200d', '')
        words = [w for w in re.split(r'(\n)|(\s+)', text) if w is not None and w != '']
        
        lines = []
        current_line = []
        current_width = 0.0

        # M4: Cache word and space widths incrementally to keep complexity at O(N)
        for word in words:
            if word == '\n':
                lines.append(''.join(current_line))
                current_line = []
                current_width = 0.0
            elif word.isspace():
                if current_line:
                    word_width = font_obj.text_length(word, fontsize=fontsize)
                    if current_width + word_width > self.max_width:
                        lines.append(''.join(current_line))
                        current_line = []
                        current_width = 0.0
                    else:
                        current_line.append(word)
                        current_width += word_width
            else:
                word_width = font_obj.text_length(word, fontsize=fontsize)
                if current_width + word_width > self.max_width and current_line:
                    lines.append(''.join(current_line))
                    current_line = [word]
                    current_width = word_width
                else:
                    current_line.append(word)
                    current_width += word_width
                    
        if current_line:
            lines.append(''.join(current_line))

        block_height = len(lines) * LINE_HEIGHT
        
        # H2: Check overflow per-line during insertion
        for line in lines:
            if self.y + LINE_HEIGHT > HEIGHT - MARGIN:
                self.add_page()
            self.page.insert_text(
                fitz.Point(MARGIN, self.y),
                line,
                fontname=registered_name,
                fontsize=fontsize,
                color=color
            )
            self.y += LINE_HEIGHT
            
        self.y += spacing
        return block_height

    def write_heading(self, text: str, level=1):
        if level == 1:
            size = 14
            font = "Helvetica-Bold"
            color = Colors.BRAND_DARK
            space_before = 18
            space_after = 8
        elif level == 2:
            size = 11
            font = "Helvetica-Bold"
            color = Colors.BRAND_MID
            space_before = 12
            space_after = 6
        else:
            size = 10
            font = "Helvetica-Bold"
            color = (0.2, 0.2, 0.45)
            space_before = 10
            space_after = 4

        # M3: Check overflow before y is incremented by space_before
        if self.y + space_before + size + space_after > HEIGHT - MARGIN:
            self.add_page()
        else:
            self.y += space_before

        registered_name, _ = self.get_font_params(font)
        self.page.insert_text(
            fitz.Point(MARGIN, self.y),
            text,
            fontname=registered_name,
            fontsize=size,
            color=color
        )
        self.y += size + space_after
        
        if level == 1:
            self.page.draw_rect(
                fitz.Rect(MARGIN, self.y - 4, WIDTH - MARGIN, self.y - 3),
                color=color,
                fill=color,
                width=1
            )
            self.y += 14

    def next_section(self, title: str) -> str:
        self.section_counter += 1
        return f"{self.section_counter}. {title}"

# ── Report Content Builder ────────────────────────────────────────────────────
def build_report_sections(doc: PDFDocument, filename: str, analysis: Any):
    # Page 1 Title Banner block
    registered_bold, _ = doc.get_font_params("Helvetica-Bold")
    doc.page.draw_rect(
        fitz.Rect(MARGIN, MARGIN, WIDTH - MARGIN, MARGIN + 40),
        color=None,
        fill=Colors.RISK_BG
    )
    doc.page.insert_text(
        fitz.Point(MARGIN + 15, MARGIN + 25),
        "DocMind AI Analysis Report",
        fontname=registered_bold,
        fontsize=18,
        color=Colors.BRAND_DARK
    )
    doc.y = MARGIN + 60

    doc.write_paragraph(f"Document Filename: {filename}", fontname="Helvetica-Bold", fontsize=10)
    doc.write_paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fontname="Helvetica", fontsize=9, color=Colors.MUTED)
    doc.y += 10

    entities: ExtractedEntities = analysis.extracted_entities or {}
    risk_flags = analysis.risk_flags or []
    summary = analysis.risk_obligation_summary or ""

    # 1. Executive Summary
    doc.write_heading(doc.next_section("Executive Risk & Obligation Summary"), level=1)
    if summary:
        paragraphs = [p.strip() for p in summary.split('\n') if p.strip()]
        for para in paragraphs:
            doc.write_paragraph(para, fontname="Helvetica", fontsize=9.5, spacing=8)
    else:
        doc.write_paragraph("No summary available.", fontname="Helvetica-Oblique", color=Colors.MUTED)
    doc.y += 10

    # 2. Contracting Parties
    doc.write_heading(doc.next_section("Contracting Parties & Signatories"), level=1)
    parties = entities.get("parties", [])
    if parties:
        for party in parties:
            doc.write_paragraph(f"• {party}", fontname="Helvetica-Bold")
    else:
        doc.write_paragraph("No parties detected.", fontname="Helvetica-Oblique", color=Colors.MUTED)
    doc.y += 10

    # 3. Core Obligations
    doc.write_heading(doc.next_section("Core Obligations & Covenants"), level=1)
    obligations = entities.get("obligations", [])
    if obligations:
        for idx, ob in enumerate(obligations):
            doc.write_paragraph(f"{idx + 1}. {ob}", spacing=6)
    else:
        doc.write_paragraph("No key obligations detected.", fontname="Helvetica-Oblique", color=Colors.MUTED)
    doc.y += 10

    # 4. Financial Terms
    doc.write_heading(doc.next_section("Financial Value & Payment Terms"), level=1)
    amounts = entities.get("amounts", [])
    if amounts:
        doc.write_paragraph(", ".join(amounts))
    else:
        doc.write_paragraph("No financial terms detected.", fontname="Helvetica-Oblique", color=Colors.MUTED)
    doc.y += 10

    # 5. Timelines
    doc.write_heading(doc.next_section("Important Timelines & Deadlines"), level=1)
    dates = entities.get("dates", [])
    if dates:
        doc.write_paragraph(", ".join(dates))
    else:
        doc.write_paragraph("No timeline terms detected.", fontname="Helvetica-Oblique", color=Colors.MUTED)
    doc.y += 10

    # 6. Risk Flags
    doc.write_heading(doc.next_section("Risk Flags & Exposure Assessment"), level=1)
    if risk_flags:
        for idx, r in enumerate(risk_flags):
            level = str(r.get("level", "low")).upper()
            clause = r.get("clause", "")
            reason = r.get("reason", "")

            # M5: Map risk level color explicitly
            badge_color = RISK_COLORS.get(level, RISK_COLORS["LOW"])

            doc.write_heading(f"Risk #{idx + 1} [{level}]", level=2)
            doc.write_paragraph("Flagged Clause:", fontname="Helvetica-Bold", fontsize=9, color=badge_color, spacing=2)
            doc.write_paragraph(f'"{clause}"', fontname="Helvetica-Oblique", fontsize=9, color=(0.25, 0.25, 0.25), spacing=4)
            doc.write_paragraph("Exposure Assessment:", fontname="Helvetica-Bold", fontsize=9, color=(0.3, 0.3, 0.3), spacing=2)
            doc.write_paragraph(reason, fontsize=9, spacing=10)
    else:
        doc.write_paragraph("No risk flags identified.", fontname="Helvetica-Oblique", color=Colors.MUTED)

# ── Main Entry Point ──────────────────────────────────────────────────────────
def generate_analysis_pdf(filename: str, analysis: Any) -> bytes:
    doc = None
    try:
        doc = fitz.open()
        pdf_doc = PDFDocument(doc)
        build_report_sections(pdf_doc, filename, analysis)
        return doc.tobytes()
    except fitz.FitzError as exc:
        logger.error("PyMuPDF rendering failed: %s", exc, exc_info=True)
        raise RuntimeError(f"PyMuPDF rendering failed: {exc}") from exc
    finally:
        if doc is not None:
            doc.close()
