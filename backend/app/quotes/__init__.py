"""Finding quotes in files and highlight positions (W1)."""

from app.quotes.pdf import PDFIUM_LOCK, UnreadablePdfError, find_pdf_quote
from app.quotes.types import HighlightRect, MatchKind, MatchMethod, PdfQuoteMatch

__all__ = [
    "PDFIUM_LOCK",
    "HighlightRect",
    "MatchKind",
    "MatchMethod",
    "PdfQuoteMatch",
    "UnreadablePdfError",
    "find_pdf_quote",
]
