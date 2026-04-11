"""Invoice PDF generator using Jinja2 + WeasyPrint."""

import logging
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


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
    output_dir: str = "./uploads/invoices",
) -> str:
    """Generate a PDF invoice and return the file path."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("default.html")

    html = template.render(
        invoice_number=invoice_number,
        hotel_name=hotel_name,
        hotel_tax_id=hotel_tax_id,
        hotel_address=hotel_address,
        guest_name=guest_name,
        guest_tax_id=guest_tax_id or "N/A",
        issue_date=issue_date.strftime("%d/%m/%Y"),
        checkin_date=checkin_date.strftime("%d/%m/%Y") if checkin_date else "N/A",
        checkout_date=checkout_date.strftime("%d/%m/%Y") if checkout_date else "N/A",
        line_items=line_items,
        subtotal=f"{subtotal:,.2f}",
        tax_rate=f"{tax_rate:.1f}",
        tax_amount=f"{tax_amount:,.2f}",
        total=f"{total:,.2f}",
        currency=currency,
    )

    output_path = str(Path(output_dir) / f"factura_{invoice_number.replace('/', '-')}_{uuid.uuid4().hex[:8]}.pdf")

    try:
        from weasyprint import HTML

        HTML(string=html).write_pdf(output_path)
    except ImportError:
        # Fallback: save as HTML if WeasyPrint is not installed
        output_path = output_path.replace(".pdf", ".html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.warning("WeasyPrint not installed, saved as HTML")

    return output_path
