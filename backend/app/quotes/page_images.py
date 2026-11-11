"""Page images for scans, and crops for the second look (decision 0012).

A PDF page with no text layer is a scan: it has no passage to cite, so it goes to the model as an
image at a size we control, and the agent boxes values on it like on a photo. A page with real
text keeps its citations and the text check.

Every pypdfium2 call here runs while holding `PDFIUM_LOCK` (see app/quotes/pdf.py), and every
pdfium object is closed before the lock is let go.
"""

import pypdfium2 as pdfium
from PIL import Image

from app.quotes.pdf import PDFIUM_LOCK, UnreadablePdfError

# A box is cropped with this much margin on each side, as a share of the box's height, and at
# least this many pixels: a box drawn tight to the glyphs mustn't cut them off. It's small
# enough that the crop stays the boxed value, not its neighbours.
CROP_MARGIN = 0.15
CROP_MARGIN_MIN_PX = 2


def pdf_pages_with_text(pdf: bytes) -> list[bool]:
    """For each page, whether it has a text layer: any character that isn't whitespace.

    Raises UnreadablePdfError when the file can't be opened as a PDF.
    """
    with PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(pdf)
        except pdfium.PdfiumError as error:
            raise UnreadablePdfError(str(error)) from error
        try:
            out: list[bool] = []
            for index in range(len(doc)):
                page = doc[index]
                try:
                    textpage = page.get_textpage()
                    try:
                        out.append(bool(textpage.get_text_range().strip()))
                    finally:
                        textpage.close()
                finally:
                    page.close()
            return out
        finally:
            doc.close()


def render_pdf_page(pdf: bytes, page_number: int, max_edge: int) -> Image.Image:
    """Page `page_number` (from 1) as an RGB image whose long edge is `max_edge` pixels.

    The whole page is drawn, uncropped, so fractions of the image are fractions of the page.
    """
    with PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(pdf)
        except pdfium.PdfiumError as error:
            raise UnreadablePdfError(str(error)) from error
        try:
            page = doc[page_number - 1]
            try:
                width, height = page.get_size()
                bitmap = page.render(scale=max_edge / max(width, height))
                try:
                    return bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            doc.close()


def crop_box(
    image: Image.Image, left: float, top: float, width: float, height: float
) -> Image.Image | None:
    """The boxed area of a page image, from a box in fractions of the page, with a small margin.

    None when nothing of the box lies on the image.
    """
    x0, y0 = left * image.width, top * image.height
    x1, y1 = (left + width) * image.width, (top + height) * image.height
    pad = max(CROP_MARGIN_MIN_PX, CROP_MARGIN * (y1 - y0))
    box = (
        max(0, round(x0 - pad)),
        max(0, round(y0 - pad)),
        min(image.width, round(x1 + pad)),
        min(image.height, round(y1 + pad)),
    )
    if box[0] >= box[2] or box[1] >= box[3] or width <= 0 or height <= 0:
        return None
    return image.crop(box)
