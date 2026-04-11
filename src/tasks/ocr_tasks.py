import logging
import uuid
from datetime import date

from src.celery_app import celery
from src.database import SessionLocal
from src.models.bank_transaction import BankTransaction
from src.models.channel_reservation import ChannelReservation
from src.models.upload import Upload

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def process_bank_statement(self, upload_id: str):
    """Extract transactions from a bank statement PDF using OCR + LLM."""
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
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery.task(bind=True, max_retries=3)
def process_channel_file(self, upload_id: str):
    """Parse a channel CSV/Excel file into structured reservations."""
    db = SessionLocal()
    try:
        upload = db.query(Upload).filter(Upload.id == uuid.UUID(upload_id)).first()
        if not upload:
            logger.error(f"Upload {upload_id} not found")
            return

        upload.status = "processing"
        db.commit()

        # Try Booking.com parser first, then generic
        from src.parsers.booking_com import BookingComParser
        from src.parsers.generic_csv import GenericCSVParser

        parser = BookingComParser()
        if parser.can_parse(upload.stored_path):
            result = parser.parse(upload.stored_path)
        else:
            parser = GenericCSVParser()
            result = parser.parse(upload.stored_path)

        if result.errors:
            logger.warning(f"Parsing errors for {upload_id}: {result.errors}")

        for r in result.reservations:
            checkin = None
            checkout = None
            if r.checkin_date:
                try:
                    checkin = date.fromisoformat(str(r.checkin_date)[:10])
                except (ValueError, TypeError):
                    pass
            if r.checkout_date:
                try:
                    checkout = date.fromisoformat(str(r.checkout_date)[:10])
                except (ValueError, TypeError):
                    pass

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
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()
