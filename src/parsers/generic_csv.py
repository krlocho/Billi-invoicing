"""Generic CSV parser that uses LLM to understand any channel file format."""

import json
import logging

import pandas as pd

from src.config import settings
from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un experto en datos de reservas hoteleras. Se te proporciona las primeras filas
de un fichero CSV de un canal de reservas (Booking.com, Expedia, Hotelbeds, Agoda, etc.).

Tu tarea es identificar qué columna corresponde a cada campo de reserva. Responde SOLO con JSON:
{
    "channel_detected": "nombre del canal detectado o 'unknown'",
    "column_mapping": {
        "reservation_id": "nombre exacto de la columna o null",
        "guest_name": "nombre exacto de la columna o null",
        "checkin_date": "nombre exacto de la columna o null",
        "checkout_date": "nombre exacto de la columna o null",
        "room_type": "nombre exacto de la columna o null",
        "nights": "nombre exacto de la columna o null",
        "gross_amount": "nombre exacto de la columna o null",
        "commission_amount": "nombre exacto de la columna o null",
        "net_amount": "nombre exacto de la columna o null",
        "currency": "nombre exacto de la columna o null",
        "status": "nombre exacto de la columna o null"
    }
}"""


class GenericCSVParser(ChannelParser):
    """Uses LLM to understand any CSV format from any booking channel."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith((".csv", ".xlsx", ".xls"))

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            if file_path.lower().endswith(".csv"):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            return ChannelFileResult(errors=[f"Failed to read file: {e}"])

        # Ask LLM to figure out the column mapping
        sample = df.head(5).to_csv(index=False)
        mapping = self._get_column_mapping(sample, list(df.columns))

        if "error" in mapping:
            return ChannelFileResult(errors=[mapping["error"]])

        col_map = mapping.get("column_mapping", {})
        channel = mapping.get("channel_detected", "unknown")

        reservations = []
        for _, row in df.iterrows():
            res = ParsedReservation(
                reservation_id=self._safe_get(row, col_map.get("reservation_id")),
                guest_name=self._safe_get(row, col_map.get("guest_name")),
                checkin_date=self._safe_get(row, col_map.get("checkin_date")),
                checkout_date=self._safe_get(row, col_map.get("checkout_date")),
                room_type=self._safe_get(row, col_map.get("room_type")),
                nights=self._safe_int(row, col_map.get("nights")),
                gross_amount=self._safe_float(row, col_map.get("gross_amount")),
                commission_amount=self._safe_float(row, col_map.get("commission_amount")),
                net_amount=self._safe_float(row, col_map.get("net_amount")),
                currency=self._safe_get(row, col_map.get("currency")) or "EUR",
                status=self._safe_get(row, col_map.get("status")),
            )
            reservations.append(res)

        return ChannelFileResult(reservations=reservations, channel_name=channel)

    def _get_column_mapping(self, sample_csv: str, columns: list[str]) -> dict:
        prompt = f"Columnas disponibles: {columns}\n\nPrimeras filas:\n{sample_csv}"

        try:
            provider = settings.default_llm_provider
            if provider == "google" and settings.google_api_key:
                from google import genai
                client = genai.Client(api_key=settings.google_api_key)
                response = client.models.generate_content(
                    model=settings.default_llm_model,
                    contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                text = response.text
            elif provider == "anthropic" and settings.anthropic_api_key:
                import anthropic
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                response = client.messages.create(
                    model=settings.default_llm_model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
            elif provider == "openai" and settings.openai_api_key:
                from openai import OpenAI
                client = OpenAI(api_key=settings.openai_api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                text = response.choices[0].message.content
            else:
                return {"error": "No LLM API key configured"}

            return json.loads(text)
        except Exception as e:
            logger.error(f"LLM column mapping failed: {e}")
            return {"error": str(e)}

    def _safe_get(self, row: pd.Series, col: str | None) -> str | None:
        if col and col in row.index and pd.notna(row[col]):
            return str(row[col]).strip()
        return None

    def _safe_float(self, row: pd.Series, col: str | None) -> float | None:
        val = self._safe_get(row, col)
        if val:
            try:
                return float(val.replace(",", ".").replace("€", "").replace("$", "").strip())
            except ValueError:
                return None
        return None

    def _safe_int(self, row: pd.Series, col: str | None) -> int | None:
        val = self._safe_get(row, col)
        if val:
            try:
                return int(float(val))
            except ValueError:
                return None
        return None
