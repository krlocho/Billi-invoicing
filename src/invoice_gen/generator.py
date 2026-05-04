"""Invoice PDF generator using ReportLab (pure Python, no external libs)."""

import logging
import uuid
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

ACCENT = colors.HexColor("#6c5ce7")
TEXT = colors.HexColor("#1a1a2e")
MUTED = colors.HexColor("#777777")
LIGHT_BG = colors.HexColor("#f4f4f8")


def _build_styles() -> dict:
    base = getSampleStyleSheet()["Normal"]
    return {
        "hotel_name": ParagraphStyle(
            "hotel_name", parent=base, fontName="Helvetica-Bold",
            fontSize=18, textColor=ACCENT, leading=22,
        ),
        "hotel_meta": ParagraphStyle(
            "hotel_meta", parent=base, fontName="Helvetica",
            fontSize=9, textColor=MUTED, leading=12,
        ),
        "invoice_title": ParagraphStyle(
            "invoice_title", parent=base, fontName="Helvetica-Bold",
            fontSize=22, textColor=ACCENT, alignment=2, leading=26,
        ),
        "invoice_meta": ParagraphStyle(
            "invoice_meta", parent=base, fontName="Helvetica",
            fontSize=10, textColor=TEXT, alignment=2, leading=14,
        ),
        "section_label": ParagraphStyle(
            "section_label", parent=base, fontName="Helvetica-Bold",
            fontSize=8, textColor=MUTED, leading=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", parent=base, fontName="Helvetica",
            fontSize=10, textColor=TEXT, leading=14,
        ),
        "body_bold": ParagraphStyle(
            "body_bold", parent=base, fontName="Helvetica-Bold",
            fontSize=11, textColor=TEXT, leading=14,
        ),
        "footer": ParagraphStyle(
            "footer", parent=base, fontName="Helvetica-Oblique",
            fontSize=8, textColor=MUTED, alignment=1, leading=10,
        ),
    }


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "N/A"


def generate_invoice_pdf(
    invoice_number: str,
    hotel_name: str,
    hotel_tax_id: str,
    hotel_address: str,
    guest_name: str,
    guest_tax_id: str | None,
    issue_date: date,
    checkin_date: date | None,
    checkout_date: date | None,
    line_items: list[dict],
    subtotal: float,
    tax_rate: float,
    tax_amount: float,
    total: float,
    currency: str = "EUR",
    tax_name: str = "IVA",
    output_dir: str = "./uploads/invoices",
) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(
        Path(output_dir)
        / f"factura_{invoice_number.replace('/', '-')}_{uuid.uuid4().hex[:8]}.pdf"
    )

    s = _build_styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Factura {invoice_number}",
    )

    story = []

    header = Table(
        [[
            [
                Paragraph(hotel_name, s["hotel_name"]),
                Paragraph(f"CIF/NIF: {hotel_tax_id}", s["hotel_meta"]),
                Paragraph(hotel_address or "", s["hotel_meta"]),
            ],
            [
                Paragraph("FACTURA", s["invoice_title"]),
                Paragraph(f"<b>N&ordm;:</b> {invoice_number}", s["invoice_meta"]),
                Paragraph(f"<b>Fecha:</b> {_fmt_date(issue_date)}", s["invoice_meta"]),
            ],
        ]],
        colWidths=[doc.width * 0.55, doc.width * 0.45],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, ACCENT),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(header)
    story.append(Spacer(1, 14))

    story.append(Paragraph("CLIENTE", s["section_label"]))
    story.append(Paragraph(f"<b>{guest_name}</b>", s["body_bold"]))
    story.append(Paragraph(f"NIF/Pasaporte: {guest_tax_id or 'N/A'}", s["body"]))
    story.append(Spacer(1, 14))

    stay = Table(
        [[
            [Paragraph("CHECK-IN", s["section_label"]),
             Paragraph(_fmt_date(checkin_date), s["body_bold"])],
            [Paragraph("CHECK-OUT", s["section_label"]),
             Paragraph(_fmt_date(checkout_date), s["body_bold"])],
        ]],
        colWidths=[doc.width * 0.5, doc.width * 0.5],
    )
    stay.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(stay)
    story.append(Spacer(1, 14))

    rows = [["Descripción", "Noches", f"Precio/Noche ({currency})", f"Importe ({currency})"]]
    for item in line_items:
        rows.append([
            item.get("description", ""),
            str(item.get("quantity", "")),
            str(item.get("unit_price", "")),
            str(item.get("amount", "")),
        ])
    items_tbl = Table(rows, colWidths=[
        doc.width * 0.46, doc.width * 0.12, doc.width * 0.21, doc.width * 0.21,
    ])
    items_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(items_tbl)
    story.append(Spacer(1, 14))

    totals_data = [
        ["Subtotal", f"{subtotal:,.2f} {currency}"],
        [f"{tax_name} ({tax_rate:.1f}%)", f"{tax_amount:,.2f} {currency}"],
        ["TOTAL", f"{total:,.2f} {currency}"],
    ]
    totals_tbl = Table(totals_data, colWidths=[doc.width * 0.6, doc.width * 0.4], hAlign="RIGHT")
    totals_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -2), 10),
        ("TEXTCOLOR", (0, 0), (-1, -2), TEXT),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("TEXTCOLOR", (0, -1), (-1, -1), ACCENT),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, ACCENT),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    totals_wrapper = Table([[totals_tbl]], colWidths=[doc.width])
    totals_wrapper.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT")]))
    story.append(totals_wrapper)

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "Generado automáticamente por Billi — Sistema de facturación inteligente para hoteles",
        s["footer"],
    ))

    doc.build(story)
    return output_path
