import io
import logging
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import bedrock_service, llamaparse_service, reminder_logic
from .i18n import t
from .models import (
    ReminderRequest,
    ReminderResponse,
    ReminderTime,
    TranslateRequest,
    TranslateResponse,
    UploadResponse,
)

logger = logging.getLogger("ubatjelas")
logging.basicConfig(level=logging.INFO)

MAX_FILE_SIZE_MB = float(os.environ.get("MAX_FILE_SIZE_MB", "10"))
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png"}
SUPPORTED_PDF_TYPES = {"application/pdf"}

app = FastAPI(title="UbatJelas Backend", version="1.0")

# Frontend is a static S3 site on a different origin than the API Gateway
# endpoint, so CORS must stay open (or scoped to the S3 site URL once known).
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def _pdf_first_page_to_image_bytes(pdf_bytes: bytes) -> bytes:
    """OCR only accepts image bytes, so a PDF's first page is rasterized to
    PNG before OCR (FSD 2.2 accepts PDF as an upload type; this keeps that
    promise without S3/async jobs)."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), session_language: str = Form("en")):
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        return UploadResponse(
            raw_text="",
            confidence_score=0.0,
            passed_confidence_check=False,
            message=t("file_too_large", session_language),
        )

    content_type = file.content_type or ""
    if content_type in SUPPORTED_PDF_TYPES:
        try:
            image_bytes = _pdf_first_page_to_image_bytes(contents)
        except Exception:
            logger.exception("PDF rasterization failed")
            raise HTTPException(status_code=502, detail=t("api_failure", session_language))
    elif content_type in SUPPORTED_IMAGE_TYPES:
        image_bytes = contents
    else:
        return UploadResponse(
            raw_text="",
            confidence_score=0.0,
            passed_confidence_check=False,
            message=t("unsupported_file", session_language),
        )

    try:
        raw_text, confidence, passed = llamaparse_service.extract_text(image_bytes)
    except Exception:
        logger.exception("LlamaParse call failed")
        raise HTTPException(status_code=502, detail=t("api_failure", session_language))

    message = None if passed else t("low_confidence", session_language)

    return UploadResponse(
        raw_text=raw_text,
        confidence_score=confidence,
        passed_confidence_check=passed,
        message=message,
    )


@app.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    try:
        result = bedrock_service.translate(req.raw_text, req.session_language)
    except Exception:
        logger.exception("Bedrock call failed")
        raise HTTPException(status_code=502, detail=t("api_failure", req.session_language))

    translated_text = result["translated_text"]
    if result.get("term_uncertain"):
        suffix = t("term_uncertain_suffix", req.session_language)
        if suffix not in translated_text:
            translated_text = f"{translated_text}\n\n{suffix}"

    return TranslateResponse(
        translated_text=translated_text,
        medicine_name=result.get("medicine_name"),
        frequency_code=result.get("frequency_code"),
        meal_relation=result.get("meal_relation"),
        duration=result.get("duration"),
        term_uncertain=result.get("term_uncertain", False),
        warning_text=t("inline_warning", req.session_language),
    )


@app.post("/reminder", response_model=ReminderResponse)
async def reminder(req: ReminderRequest):
    proposed, source, note = reminder_logic.compute_reminders(
        req.frequency_code, req.meal_relation, req.manual_times, req.session_language
    )
    return ReminderResponse(
        proposed_times=[ReminderTime(**p) for p in proposed],
        source=source,
        note=note,
    )
