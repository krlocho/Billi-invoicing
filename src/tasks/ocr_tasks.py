import logging
import uuid
from datetime import date, datetime


def _coerce_date(value) -> date | None:
    """Parse dates from any common format channel CSVs use."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try the formats we actually see in channel exports, ISO first.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None

from src.celery_app import celery
from src.database import SessionLocal
from src.models.bank_transaction import BankTransaction
from src.models.channel_reservation import ChannelReservation
from src.models.upload import Upload

logger = logging.getLogger(__name__)


def _process_bank_statement_sync(upload_id: str):
    """Sync fallback when Celery is not available."""
    _do_process_bank_statement(upload_id, celery_task=None)


@celery.task(bind=True, max_retries=3)
def process_bank_statement(self, upload_id: str):
    """Extract transactions from a bank statement PDF using OCR + LLM."""
    _do_process_bank_statement(upload_id, celery_task=self)


def _do_process_bank_statement(upload_id: str, celery_task=None):
    db = SessionLocal()
    try:
        upload = db.query(Upload).filter(Upload.id == uuid.UUID(upload_id)).first()
        if not upload:
            logger.error(f"Upload {upload_id} not found")
            return

        upload.status = "processing"
        db.commit()

        # Step 1: Extract raw text from PDF
        from src.ocr.digital_pdf import DigitalPDFExtractor

        extractor = DigitalPDFExtractor()
        result = extractor.extract(upload.stored_path)

        # If digital extraction failed, try Tesseract
        if not result.raw_text.strip():
            try:
                from src.ocr.tesseract import TesseractExtractor

                extractor = TesseractExtractor()
                result = extractor.extract(upload.stored_path)
            except ImportError:
                logger.warning("Tesseract not available, using digital PDF only")

        if not result.raw_text.strip():
            upload.status = "failed"
            upload.error_message = "Could not extract text from PDF"
            db.commit()
            return

        upload.raw_text = result.raw_text

        # Step 2: Use LLM to structure the extracted text into transactions
        from src.ocr.llm_extractor import extract_with_llm

        llm_result = extract_with_llm(result.raw_text)

        if llm_result.errors:
            logger.warning(f"LLM extraction errors: {llm_result.errors}")

        # Step 3: Store structured transactions
        for t in llm_result.transactions:
            try:
                tx_date = date.fromisoformat(t.date)
            except (ValueError, TypeError):
                continue

            value_date = None
            if t.value_date:
                try:
                    value_date = date.fromisoformat(t.value_date)
                except (ValueError, TypeError):
                    pass

            transaction = BankTransaction(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                transaction_date=tx_date,
                value_date=value_date,
                description=t.description,
                amount=t.amount,
                balance=t.balance,
                raw_text=t.raw_text,
            )
            db.add(transaction)

        upload.status = "completed"
        db.commit()
        logger.info(
            f"Processed bank statement {upload_id}: {len(llm_result.transactions)} transactions"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing bank statement {upload_id}: {e}")
        upload = db.query(Upload).filter(Upload.id == uuid.UUID(upload_id)).first()
        if upload:
            upload.status = "failed"
            upload.error_message = str(e)
            db.commit()
        if celery_task:
            raise celery_task.retry(exc=e, countdown=60)
    finally:
        db.close()


def _process_channel_file_sync(upload_id: str):
    """Sync fallback when Celery is not available."""
    _do_process_channel_file(upload_id, celery_task=None)


@celery.task(bind=True, max_retries=3)
def process_channel_file(self, upload_id: str):
    """Parse a channel CSV/Excel file into structured reservations."""
    _do_process_channel_file(upload_id, celery_task=self)


def _do_process_channel_file(upload_id: str, celery_task=None):
    db = SessionLocal()
    try:
        upload = db.query(Upload).filter(Upload.id == uuid.UUID(upload_id)).first()
        if not upload:
            logger.error(f"Upload {upload_id} not found")
            return

        upload.status = "processing"
        db.commit()

        # Try channel-specific parsers first; fall back to LLM-driven generic.
        from src.parsers.airbnb import AirbnbParser
        from src.parsers.booking_com import BookingComParser
        from src.parsers.expedia import ExpediaParser
        from src.parsers.generic_csv import GenericCSVParser
        from src.parsers.stripe import StripeParser

        result = None
        for parser in (BookingComParser(), AirbnbParser(), StripeParser(), ExpediaParser()):
            if parser.can_parse(upload.stored_path):
                result = parser.parse(upload.stored_path)
                break
        if result is None:
            result = GenericCSVParser().parse(upload.stored_path)

        if result.errors:
            logger.warning(f"Parsing errors for {upload_id}: {result.errors}")

        for r in result.reservations:
            checkin = _coerce_date(r.checkin_date)
            checkout = _coerce_date(r.checkout_date)

            reservation = ChannelReservation(
                upload_id=upload.id,
                tenant_id=upload.tenant_id,
                channel_id=upload.channel_id,
                reservation_id=r.reservation_id,
                guest_name=r.guest_name,
                checkin_date=checkin,
                checkout_date=checkout,
                room_type=r.room_type,
                nights=r.nights,
                gross_amount=r.gross_amount,
                commission_amount=r.commission_amount,
                net_amount=r.net_amount,
                currency=r.currency,
                status=r.status,
                payout_ref=r.payout_ref,
                extra_data=r.extra_data,
            )
            db.add(reservation)

        upload.status = "completed"
        db.commit()
        logger.info(
            f"Processed channel file {upload_id}: {len(result.reservations)} reservations"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing channel file {upload_id}: {e}")
        upload = db.query(Upload).filter(Upload.id == uuid.UUID(upload_id)).first()
        if upload:
            upload.status = "failed"
            upload.error_message = str(e)
            db.commit()
        if celery_task:
            raise celery_task.retry(exc=e, countdown=60)
    finally:
        db.close()
