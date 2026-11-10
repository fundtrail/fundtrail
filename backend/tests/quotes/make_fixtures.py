"""Regenerate the test PDFs in fixtures/. Not run by the tests; the PDFs are committed.

Run from backend/:  uv run python -m tests.quotes.make_fixtures [path to the two govinfo PDFs]

Every name, award number and address in the made-up files is synthetic (award numbers start with
SYN-, addresses use .example). The files come from three producers, so the tests see more than
one way of writing text into a PDF:

- reportlab (a dev dependency): invoice_reportlab.pdf, letter_reportlab.pdf and
  hyphenated_reportlab.pdf.
- Headless Google Chrome printing an HTML page, with automatic hyphenation and justified text:
  memo_chrome.pdf. Needs Chrome installed; skipped otherwise.
- The U.S. Government Publishing Office (GPO): ecfr_2cfr200.pdf, two printed pages of 2 CFR part
  200 (2025 edition), public federal text, cut from these two govinfo files:
  https://www.govinfo.gov/content/pkg/CFR-2025-title2-vol1/pdf/CFR-2025-title2-vol1-sec200-403.pdf
  https://www.govinfo.gov/content/pkg/CFR-2025-title2-vol1/pdf/CFR-2025-title2-vol1-sec200-453.pdf
  Pass their local paths to rebuild it.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FIXTURES = Path(__file__).parent / "fixtures"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def invoice(path: Path) -> None:
    """A one-page bill drawn line by line, with a small table of items."""
    c = canvas.Canvas(str(path), pagesize=letter, invariant=True)
    c.setTitle("Invoice INV-SYN-0042")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 720, "Northfield Lab Supply Co.")
    c.setFont("Helvetica", 10)
    lines = [
        "1200 Example Parkway, Suite 4, Northfield, CA 94000",
        "billing@northfield-supply.example",
        "",
        "Invoice number: INV-SYN-0042",
        "Invoice date: March 3, 2026",
        "Bill to: Department of Molecular Biology, Synthetic University",
        "Award: SYN-2025-0117 (PI: Dr. Rowan Ellery)",
    ]
    y = 700
    for line in lines:
        c.drawString(72, y, line)
        y -= 14
    y -= 10
    c.setFont("Helvetica-Bold", 10)
    for x, head in ((72, "Item"), (330, "Qty"), (380, "Unit price"), (470, "Amount")):
        c.drawString(x, y, head)
    c.setFont("Helvetica", 10)
    rows = [
        ("Pipette tips, 1000 uL, sterile (case)", "12", "$85.00", "$1,020.00"),
        ("Nitrile gloves, size M (box of 100)", "40", "$14.50", "$580.00"),
        ("Benchtop centrifuge, 24-place rotor", "1", "$9,850.00", "$9,850.00"),
        ("Freight and handling", "1", "$1,000.00", "$1,000.00"),
    ]
    for item, qty, unit, amount in rows:
        y -= 16
        c.drawString(72, y, item)
        c.drawString(330, y, qty)
        c.drawString(380, y, unit)
        c.drawString(470, y, amount)
    y -= 26
    c.setFont("Helvetica-Bold", 11)
    c.drawString(380, y, "Total due:")
    c.drawString(470, y, "$12,450.00")
    c.setFont("Helvetica", 9)
    c.drawString(72, y - 30, "Payment terms: net 30 days. Please reference the invoice number")
    c.drawString(72, y - 42, "on all remittances. Questions: billing@northfield-supply.example.")
    c.save()


LETTER_FILLER = (
    "The project studies how soil microbes respond to seasonal drought across three field "
    "sites. Work in the second year focused on sample collection, sequencing and the first "
    "round of analysis, and the team stayed within the approved budget for each category. "
)


def award_letter(path: Path) -> None:
    """A two-page letter set by reportlab's layout engine, justified, wrapping on its own."""
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=styles["BodyText"], alignment=TA_JUSTIFY, fontSize=11, leading=15
    )
    story = [
        Paragraph("Synthetic Science Foundation", styles["Title"]),
        Paragraph("Award notice for SYN-2025-0117", styles["Heading2"]),
        Paragraph(
            "Dear Dr. Ellery: The Synthetic Science Foundation is pleased to inform you that "
            "award SYN-2025-0117 has been made in the amount of $120,000 for the period "
            "September 1, 2025 through August 31, 2027. This award is subject to the terms "
            "and conditions incorporated by reference in this letter.",
            body,
        ),
        Spacer(1, 8),
        Paragraph(
            "Participant support costs of $20,000 may not be rebudgeted into other categories "
            "without the prior written approval of the cognizant program officer. Requests "
            "must be sent to grants-office@ssf.example at least thirty days before the change.",
            body,
        ),
        Spacer(1, 8),
    ]
    for _ in range(3):
        story.append(Paragraph(LETTER_FILLER * 2, body))
        story.append(Spacer(1, 8))
    # This paragraph runs across the page break.
    story.append(
        Paragraph(
            "Equipment purchased under this award with a unit cost of $5,000 or more must be "
            "recorded in the university's property system within sixty days of receipt, and "
            "the record must name the award number and the location of the item. Items bought "
            "in the last ninety days of the award period need a written justification that "
            "explains why the purchase was necessary to complete the project. The justification "
            "is kept with the purchase record and is reviewed at closeout together with the "
            "property record, the invoice and the proof of payment. Where an item is shared "
            "with another project, the record must also show how its cost was divided between "
            "the projects and the basis used for the division, such as hours of use or the "
            "number of samples processed for each project during the award period. Fabricated "
            "equipment is recorded when it is placed in service, at the total cost of its "
            "components, labor and any services bought to build it, and its record must list "
            "the invoices for those components so that each one can be traced to a charge.",
            body,
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Questions about this letter may be directed to Morgan Tate, Grants Officer, at "
            "mtate@ssf.example.",
            body,
        )
    )
    doc = SimpleDocTemplate(
        str(path), pagesize=letter, invariant=True, title="Award notice SYN-2025-0117"
    )
    doc.build(story)


def hyphenated(path: Path) -> None:
    """Hand-set lines that break words with a hyphen, then a rotated page with a crop box."""
    c = canvas.Canvas(str(path), pagesize=letter, invariant=True)
    c.setTitle("Budget justification")
    c.setFont("Times-Roman", 12)
    lines = [
        "Budget justification for award SYN-2025-0117, year two.",
        "",
        "The sequencing core will charge an internal recharge rate ap-",
        "proved by the university for each run, and the project expects",
        "twelve runs during the year. Cost-sharing commitments are not",
        "required by the solicitation, and none are proposed. The PI's",
        "summer salary is requested at one month, consistent with the uni-",
        "versity's policy on academic-year appointments. Travel funds sup-",
        "port two trips to the annual meeting of the Synthetic Soil Soci-",
        "ety, where the team will present results from the field sites.",
        "Materials and supplies include sterile consumables and reagents",
        "for DNA extraction; the requested amount is based on the cost-",
        "sharing quote and on prices paid in year one, adjusted for infla-",
        "tion at three percent.",
    ]
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.showPage()

    # Page 2: shown turned a quarter turn, with a crop box that doesn't start at the origin.
    c.setPageRotation(90)
    c.setCropBox((36, 36, 576, 756))
    c.setFont("Helvetica", 12)
    c.drawString(100, 600, "Rotated page: the approved carryover amount is $4,200.00.")
    c.drawString(100, 580, "This note was scanned sideways and saved with its rotation.")
    c.showPage()
    c.save()


MEMO_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Approval memo SYN-2025-0117</title>
<style>
  body { font-family: Georgia, "Times New Roman", serif; font-size: 12pt; margin: 0.8in; }
  .col { width: 3.2in; text-align: justify; hyphens: auto; -webkit-hyphens: auto; }
  table { border-collapse: collapse; margin-top: 12pt; }
  td, th { border: 1px solid #999; padding: 3pt 8pt; text-align: left; }
  td.n { text-align: right; }
</style></head>
<body>
<h2>Approval memo</h2>
<div class="col">
<p>From: Morgan Tate &lt;mtate@ssf.example&gt;<br>
To: Rowan Ellery &lt;rellery@synthetic-u.example&gt;<br>
Date: April 14, 2026</p>
<p>After reviewing the justification, the program office approves the reallocation of
$6,500 from participant support to materials and supplies for award SYN-2025-0117. The
reallocation is effective immediately and doesn&rsquo;t change the total award amount.</p>
<p>This approval is specific to the &ldquo;field sampling expansion&rdquo; described in your
request of March 30, 2026. It doesn&rsquo;t authorize any other rebudgeting, and
notwithstanding this approval the institution remains responsible for demonstrating that
every charge is allowable, allocable and reasonable under the applicable cost principles.</p>
<p>Specifically, the office finds the proposed configuration of fieldwork instrumentation
financially justifiable. Undocumented reimbursement requests will be disallowed.</p>
<p>Please keep this memo with the award file &mdash; it will be needed at closeout.</p>
</div>
<table>
<tr><th>Category</th><th>Before</th><th>After</th></tr>
<tr><td>Participant support</td><td class="n">$20,000</td><td class="n">$13,500</td></tr>
<tr><td>Materials and supplies</td><td class="n">$40,000</td><td class="n">$46,500</td></tr>
</table>
</body></html>
"""


def chrome_memo(path: Path) -> None:
    """A memo printed by headless Chrome, with automatic hyphenation and justified text."""
    if not CHROME.exists():
        print("Chrome not found; keeping the committed memo_chrome.pdf")
        return
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "memo.html"
        html.write_text(MEMO_HTML, encoding="utf-8")
        subprocess.run(
            [
                str(CHROME),
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={path}",
                html.as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def ecfr_pages(path: Path, sources: list[Path]) -> None:
    """Join the first page of each govinfo file into one PDF."""
    out = pdfium.PdfDocument.new()
    for source in sources:
        src = pdfium.PdfDocument(source)
        out.import_pages(src, [0])
        src.close()
    out.save(path)
    out.close()


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    invoice(FIXTURES / "invoice_reportlab.pdf")
    award_letter(FIXTURES / "letter_reportlab.pdf")
    hyphenated(FIXTURES / "hyphenated_reportlab.pdf")
    chrome_memo(FIXTURES / "memo_chrome.pdf")
    if len(sys.argv) == 3:
        ecfr_pages(FIXTURES / "ecfr_2cfr200.pdf", [Path(a) for a in sys.argv[1:]])
    else:
        print("No govinfo files given; keeping the committed ecfr_2cfr200.pdf")


if __name__ == "__main__":
    main()
