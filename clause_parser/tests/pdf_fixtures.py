"""Shared PDF-building helpers for tests exercising PDF ingestion
(§2.1/§5.1/§7, spec_version 1.1.0). Not a test module itself — imported by
unit/integration tests that need real PDF bytes without a PDF-writing
dependency beyond pypdf (already a project dependency, used only for the
blank-page case)."""

from __future__ import annotations
from io import BytesIO

import pypdf


def minimal_pdf_with_text(text: str) -> bytes:
    """Builds a minimal, valid single-page PDF containing `text` as real
    content-stream text-showing operations — offsets computed
    programmatically, no external PDF-writing dependency. `text` may contain
    '\\n'; each line becomes its own text-showing operation on its own line
    (so extraction yields genuine line breaks, matching real multi-line legal
    documents), one line per Td move. Lines must not contain PDF
    string-literal special characters ('(', ')', '\\')."""
    lines = text.split("\n")
    ops = [f"BT /F1 12 Tf 72 720 Td ({lines[0]}) Tj"]
    for line in lines[1:]:
        ops.append(f"0 -14 Td ({line}) Tj")
    ops.append("ET")
    content = "\n".join(ops)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        "/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]

    pdf = "%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf.encode("latin-1")))
        pdf += f"{i} 0 obj\n{obj}\nendobj\n"
    xref_offset = len(pdf.encode("latin-1"))
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    return pdf.encode("latin-1")


def blank_pdf() -> bytes:
    """A structurally valid PDF with a page but no text content — the
    scanned/image-only case (no text layer to extract)."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()
