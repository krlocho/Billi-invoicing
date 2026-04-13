"""LLM-based extraction: the AI interprets raw OCR text and structures it into transactions."""

import json
import logging

from src.config import settings
from src.ocr.base import BankStatementResult, ExtractedTransaction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un experto en análisis de extractos bancarios de hoteles en España.

Tu tarea es extraer TODAS las transacciones de un extracto bancario. Para cada transacción extrae:
- date: fecha de la transacción (formato YYYY-MM-DD)
- value_date: fecha valor si aparece (formato YYYY-MM-DD o null)
- description: concepto/descripción completa
- amount: importe (positivo para ingresos, negativo para cargos)
- balance: saldo tras la operación (o null si no aparece)

Presta especial atención a:
- Pagos de canales de reservas (Booking.com, Expedia, Hotelbeds, Agoda, etc.)
- Transferencias SEPA que pueden ser pagos agrupados de channels
- El concepto bancario puede incluir referencias a reservas o nombres de huéspedes

Responde SOLO con JSON válido, sin texto adicional. Formato:
{
    "bank_detected": "nombre del banco si lo identificas o null",
    "transactions": [
        {
            "date": "2024-01-15",
            "value_date": "2024-01-15",
            "description": "BOOKING.COM BV - PAGO RESERVAS",
            "amount": 1250.00,
            "balance": 15340.50
        }
    ]
}"""


def extract_with_llm(raw_text: str) -> BankStatementResult:
    """Use LLM to structure raw OCR text into bank transactions."""
    provider = settings.default_llm_provider

    if provider == "google" and settings.google_api_key:
        return _extract_google(raw_text)
    elif provider == "anthropic" and settings.anthropic_api_key:
        return _extract_anthropic(raw_text)
    elif provider == "openai" and settings.openai_api_key:
        return _extract_openai(raw_text)
    else:
        return BankStatementResult(
            raw_text=raw_text,
            errors=["No LLM API key configured. Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY."],
        )


def _extract_anthropic(raw_text: str) -> BankStatementResult:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=settings.default_llm_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Extrae todas las transacciones de este extracto bancario:\n\n{raw_text}",
            }
        ],
    )

    return _parse_llm_response(response.content[0].text, raw_text)


def _extract_openai(raw_text: str) -> BankStatementResult:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Extrae todas las transacciones de este extracto bancario:\n\n{raw_text}",
            },
        ],
        response_format={"type": "json_object"},
    )

    return _parse_llm_response(response.choices[0].message.content, raw_text)


def _extract_google(raw_text: str) -> BankStatementResult:
    from google import genai

    client = genai.Client(api_key=settings.google_api_key)

    response = client.models.generate_content(
        model=settings.default_llm_model,
        contents=f"{SYSTEM_PROMPT}\n\nExtrae todas las transacciones de este extracto bancario:\n\n{raw_text}",
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return _parse_llm_response(response.text, raw_text)


def _parse_llm_response(response_text: str, raw_text: str) -> BankStatementResult:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response_text[start:end])
            except json.JSONDecodeError:
                return BankStatementResult(
                    raw_text=raw_text, errors=["LLM response was not valid JSON"]
                )
        else:
            return BankStatementResult(
                raw_text=raw_text, errors=["LLM response was not valid JSON"]
            )

    transactions = []
    for t in data.get("transactions", []):
        transactions.append(
            ExtractedTransaction(
                date=t.get("date", ""),
                value_date=t.get("value_date"),
                description=t.get("description", ""),
                amount=float(t.get("amount", 0)),
                balance=float(t["balance"]) if t.get("balance") is not None else None,
                raw_text=t.get("description", ""),
            )
        )

    return BankStatementResult(
        transactions=transactions,
        raw_text=raw_text,
        bank_detected=data.get("bank_detected"),
    )
