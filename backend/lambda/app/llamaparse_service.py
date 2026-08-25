"""
FSD 2.3 — OCR Extraction business logic (LlamaParse edition):
  1. Send file to LlamaParse.
  2. Retrieve the parsed text.
  3. LlamaParse does not expose a per-line confidence score the way
     Textract did. This uses a heuristic instead: extraction "passes" if a
     meaningful amount of text came back. This is a deliberate
     simplification vs. Textract's real confidence percentage — flag this
     in your README/demo if judges ask about the low-confidence rejection
     path, since the underlying signal changed even though the behavior
     (halt before translation on a bad read) is preserved.
  4. Decision rule: passed -> proceed. Else halt, no translation attempted.
"""
import os
import tempfile

from llama_cloud_services import LlamaParse

# Minimum extracted-character count to consider the read usable. Tune this
# against a few real label photos — it's a much cruder gate than Textract's
# 0-100 confidence score, so it's worth sanity-checking with a deliberately
# blurry test image (per your PRD's low-confidence success metric).
MIN_CHARS_THRESHOLD = int(os.environ.get("MIN_CHARS_THRESHOLD", "20"))

_parser = None


def _client():
    global _parser
    if _parser is None:
        _parser = LlamaParse(
            api_key=os.environ["LLAMA_CLOUD_API_KEY"],
            result_type="text",
            verbose=False,
        )
    return _parser


def _guess_extension(file_bytes: bytes) -> str:
    if file_bytes.startswith(b"\x89PNG"):
        return ".png"
    if file_bytes.startswith(b"\xff\xd8"):
        return ".jpg"
    # main.py's PDF path always rasterizes to PNG before calling here, so
    # PNG is a safe default for anything else that slips through.
    return ".png"


def extract_text(file_bytes: bytes):
    """
    Calls LlamaParse on the given image bytes.

    Returns: (raw_text: str, aggregate_confidence: float, passed: bool)
    Same return shape as textract_service.extract_text, so main.py only
    needs the import swapped, not the /upload route logic.
    """
    suffix = _guess_extension(file_bytes)

    # LlamaParse's SDK reads from a file path, so write the bytes to a temp
    # file first. delete=False + a manual close/unlink (rather than a `with`
    # block that holds the file open) is required for this to work on
    # Windows: an open NamedTemporaryFile is locked there, so the SDK can't
    # open the same path to read it while we're still holding it. tempfile's
    # default directory is used rather than a hardcoded /tmp so this also
    # runs correctly on Windows during local testing, not just on Lambda.
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(file_bytes)
        tmp.close()
        documents = _client().load_data(tmp.name)
    finally:
        os.unlink(tmp.name)

    raw_text = "\n".join(doc.text for doc in documents).strip()

    passed = len(raw_text) >= MIN_CHARS_THRESHOLD
    # 100/0 stand in for Textract's old 0-100 aggregate so downstream code
    # (which expects a float in that range) doesn't need to change.
    aggregate_confidence = 100.0 if passed else 0.0

    return raw_text, aggregate_confidence, passed
