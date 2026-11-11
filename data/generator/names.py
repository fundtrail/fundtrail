"""Every name the two samples use: the one place to change a person, a vendor or a place.

The samples' names are invented and were each checked by web search for a real
namesake (the list and the checks are in data/README.md and the pull request for
issue 281). Email addresses are the first initial and last name at a domain built
from the organization's name, ending `.example`. The National Science Foundation
(NSF) is named as the funder, with its real division abbreviations and assistance
listings, which are agency units. Nobody named here is a real official.

`LEGACY` holds the placeholder names the two unused seed grants in `data/demo/`
were built with. They keep them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Person:
    name: str
    email: str
    role: str = ""

    @property
    def last_first(self) -> str:
        first, last = self.name.split(" ", 1)
        return f"{last} {first[0]}"

    @property
    def first(self) -> str:
        return self.name.split()[0]


@dataclass(frozen=True)
class Vendor:
    name: str
    address: str
    email: str
    prefix: str
    catalog: tuple[tuple[str, int], ...] = ()
    look: str | None = None  # the vendor's own invoice look (typeset.INVOICE_LOOKS)
    account: str | None = None  # the university's account number with the vendor


@dataclass(frozen=True)
class Org:
    """The organizations a grant's documents name besides its own people and vendors."""

    university: str
    address: str
    grants_inbox: tuple[str, str]
    grants_official: tuple[str, str]
    awarding_official: tuple[str, str]
    airline: str
    airline_email: str
    flight_code: str
    home_airport: str


LEGACY = Org(
    university="University of Example",
    address="100 Example Hall, Example City, CA 94000",
    grants_inbox=("Earth and Ocean Sciences Grants", "grants@university.example"),
    grants_official=("Avery Ledger", "avery.ledger@funder.example"),
    awarding_official=("Morgan Signet", "morgan.signet@funder.example"),
    airline="Example Air",
    airline_email="receipts@exampleair.example",
    flight_code="EX",
    home_airport="EXC",
)

# ---------------------------------------------------------------- the samples

UNIVERSITY = "Halden University"
CITY = "Port Calloway"
UNIVERSITY_ADDRESS = f"1 University Drive, {CITY}, CA 94000"
DEPARTMENT = "Department of Earth and Ocean Sciences"

SAMPLES = Org(
    university=UNIVERSITY,
    address=UNIVERSITY_ADDRESS,
    grants_inbox=("Earth and Ocean Sciences Grants", "eosgrants@halden.example"),
    grants_official=("Carolyn Whitfield", "cwhitfield@nsf.example"),
    awarding_official=("Marcus Delacroix", "mdelacroix@nsf.example"),
    airline="Altamont Airlines",
    airline_email="receipts@altamontair.example",
    flight_code="AL",
    home_airport="SFO",
)

# The larger sample's people.
MAREN = Person("Maren Holloway", "mholloway@halden.example", "Principal Investigator")
TOBIAS = Person("Tobias Lindqvist", "tlindqvist@halden.example", "Co-Principal Investigator")
IMOGEN = Person("Imogen Castellano", "icastellano@halden.example", "Postdoctoral Scholar")
SIMONE = Person("Simone Brandt", "sbrandt@halden.example", "Principal Investigator")
GAIL = Person("Gail Petrakis", "gpetrakis@halden.example")  # the department's accountant
RENATA = Person("Renata Sokolova", "rsokolova@nsf.example")  # NSF program officer
SHARED_LABS = "Holloway and Brandt labs"

# The small sample's people.
OWEN = Person("Owen Marchetti", "omarchetti@halden.example", "Principal Investigator")
LIONEL = Person("Lionel Abara", "labara@nsf.example")  # NSF program officer

# The larger sample's project and places.
MARSH_TITLE = (
    "Collaborative Research: Salt Marsh Carbon Burial Under Nutrient Enrichment and Sea-Level Rise"
)
MARSH_SITE = "Carrow Point"
MARSH_DIVISION = "DEB"
MARSH_LISTING = "47.074 Biological Sciences"
ISOTOPE_FACILITY = "Halden Stable Isotope Facility"
MARINE_STATION = "Halden Marine Station at Carrow Point"

# The small sample's project and places.
SENSORS_TITLE = "Low-Cost Nitrate Sensors for Tolliver Valley Groundwater"
VALLEY = "Tolliver Valley"
VALLEY_FARM = f"{VALLEY}, CA"
VALLEY_INN = "Tolliver Valley Motor Inn"
VALLEY_AIRPORT = "FAT"
SENSORS_DIVISION = "EAR"
SENSORS_LISTING = "47.050 Geosciences"
HARDWARE = "Port Calloway Hardware"
HARDWARE_ADDRESS = ("412 MERIDIAN AVE", "PORT CALLOWAY CA 94002")

# Travel: the meetings, where they're held, and who the traveler pays.
TAXI = "Platte River Taxi"
TAXI_CITY = "Denver, Colorado"
FALL_MEETING = "Coastal Geosciences Union Fall Meeting"
FALL_MEETING_CITY = "Denver, CO"
FALL_MEETING_AIRPORT = "DEN"
FALL_MEETING_HOTEL = "Hotel Ashgrove Denver"
ESTUARIES_MEETING = "Estuarine Carbon Science Conference"
ESTUARIES_CITY = "New Bedford, MA"
ESTUARIES_AIRPORT = "BOS"
ESTUARIES_HOTEL = "Wharfside Inn New Bedford"
SOCIETY = "Pacific Coastal Science Society"
SOCIETY_MEETING = "Pacific Coastal Science Meeting"
SOCIETY_EMAIL = "registration@pacificcoastalscience.example"

# The vendors. Each keeps its invoice number prefix, which the ledger's references
# and the files' names carry. The catalogs only size the seed's draws of ordinary
# purchases; the samples' own lines are written out in larger.py and scratch.py.
CALDER = Vendor(
    "Calder Laboratory Supply",
    f"200 Quarry Parkway, {CITY}, CA 94001",
    "orders@calderlab.example",
    "INV",
    (
        ("Sediment core liners, 50 count", 24800),
        ("Nitrile gloves, medium, case of 1000", 8950),
        ("Pipette tips, 1000 uL, 10 racks", 6420),
        ("Sample bags, sterile, 500 count", 9600),
        ("Glass fiber filters, 47 mm, 100 count", 7380),
        ("Cryovials, 2 mL, 500 count", 11250),
        ("Ethanol, 200 proof, 4 L", 15600),
    ),
    look="centered",
    account="204417",
)
KITTREDGE = Vendor(
    "Kittredge Scientific",
    "55 Foundry Road, Marlow Junction, CA 94010",
    "billing@kittredgescientific.example",
    "ESS",
    (
        ("Sample bottles, acid washed, 125 mL, 72", 13440),
        ("Balance calibration weights, set", 21500),
        ("Crucibles, porcelain, 50 count", 18900),
        ("Hydrochloric acid, trace metal, 2.5 L", 16420),
        ("Tin capsules, 5 x 9 mm, 1000 count", 9875),
    ),
    look="paper",
    account="118820",
)
SALTGRASS = Vendor(
    "Saltgrass Field Supply",
    f"9 Cannery Wharf, {CITY}, CA 94020",
    "accounts@saltgrassfield.example",
    "EFG",
    (
        ("Waders, chest, size L", 18900),
        ("Field notebooks, waterproof, 12 pack", 7200),
        ("Sediment corer replacement head", 42500),
        ("GPS unit batteries, 24 pack", 3600),
        ("Dry bags, 20 L, 4 pack", 8800),
    ),
    look="grid",
    account="030561",
)
LOOMIS = Vendor(
    "Loomis Bioscience",
    f"410 Tidewater Boulevard, {CITY}, CA 94003",
    "billing@loomisbio.example",
    "EGS",
    look="ledger",
    account="077103",
)
TANNERY = Vendor(
    "Tannery Row Electronics",
    f"300 Tannery Row, {CITY}, CA 94007",
    "invoices@tanneryrowelectronics.example",
    "EES",
    look="strip",
    account="041276",
)

# What each vendor's invoice prints beside a line: its catalog number, in the
# vendor's own format, and the unit of measure (each, case or pack).
CATALOG: dict[str, tuple[str, str]] = {
    # Calder Laboratory Supply
    "Sediment core liners, 50 count": ("CL-20417", "CS"),
    "Nitrile gloves, powder free, medium, 10 boxes": ("CL-11830", "CS"),
    "Sample bags, sterile, 500 count": ("CL-30562", "PK"),
    "Core liner end caps, 100 count": ("CL-20431", "PK"),
    "Labeling tape, 19 mm, 12 rolls": ("CL-48210", "PK"),
    "Cryovials, 2 mL, 500 count": ("CL-55102", "CS"),
    "Ethanol, 200 proof, 4 L": ("CL-70044", "EA"),
    "Cryogenic storage boxes, 81 place, 5 pack": ("CL-55190", "PK"),
    "Cryogenic labels, 1000 count": ("CL-48377", "PK"),
    # Kittredge Scientific
    "Crucibles, porcelain, 50 count": ("KS-204-050", "CS"),
    "Crucible lids, porcelain, 50 count": ("KS-205-050", "CS"),
    "Crucible tongs, stainless, 9 in": ("KS-212-009", "EA"),
    "Tin capsules, 5 x 9 mm, 1000 count": ("KS-771-5X9", "PK"),
    "Sediment trap frames, stainless": ("KS-640-STF", "EA"),
    "Sediment trap collection tubes, acrylic": ("KS-641-ACT", "EA"),
    "Balance calibration weights, set": ("KS-118-SET", "EA"),
    "Weighing boats, aluminum, 250 count": ("KS-130-250", "PK"),
    "Forceps, anti-static, stainless": ("KS-215-AST", "EA"),
    "Nitrate standard solution, 1000 ppm": ("KS-903-NO3", "EA"),
    "Ionic strength adjuster, 500 mL": ("KS-905-ISA", "EA"),
    "Volumetric flasks, 100 mL, class A, 2 pack": ("KS-310-100", "PK"),
    "pH buffer set, 4, 7 and 10, 500 mL": ("KS-920-PHB", "EA"),
    # Saltgrass Field Supply
    "Field notebooks, waterproof, 12 pack": ("SG-1042", "PK"),
    "Waders, chest, size L": ("SG-2210-L", "EA"),
    "Dry bags, 20 L, 4 pack": ("SG-3320", "PK"),
    "Dry bags, 10 L, 4 pack": ("SG-3310", "PK"),
    "Wading boots, size 10": ("SG-2260-10", "EA"),
    "Wader repair kit": ("SG-2291", "EA"),
    "Field crew dinner with wine, after sampling": ("SG-MISC", "EA"),
    "Sediment corer, piston type, 1 m": ("SG-7100", "EA"),
    "Core extruder, 7 cm": ("SG-7140", "EA"),
    "Corer extension rod, 1 m": ("SG-7112", "EA"),
    "Sediment corer replacement head": ("SG-7105", "EA"),
    "Piston seals, corer, 10 pack": ("SG-7108", "PK"),
    # Loomis Bioscience
    "16S library prep kit, 96 reactions": ("LB-16S-096", "EA"),
    # Tannery Row Electronics
    "Nitrate ion-selective electrode": ("TRE-40812", "EA"),
    "Microcontroller board": ("TRE-10255", "EA"),
    "Sensor cable, 5 m": ("TRE-22705", "EA"),
    "Electrode filling solution, 125 mL": ("TRE-40830", "EA"),
    "Waterproof cable glands, 10 pack": ("TRE-22760", "PK"),
    "Sensor housing, PVC, machined": ("TRE-61040", "EA"),
    "O-ring kit": ("TRE-61077", "PK"),
    "Housing end caps, threaded, PVC": ("TRE-61052", "EA"),
    "Sensor circuit board, assembled": ("TRE-10310", "EA"),
    "Pin header kit, 2.54 mm": ("TRE-10398", "PK"),
    "Conformal coating, per board": ("TRE-10344", "EA"),
}


def lines(*items: tuple[str, int, int]) -> list[tuple[str, int, int, str, str]]:
    """Invoice lines (description, quantity, unit cents) with each one's catalog number
    and unit of measure."""
    return [(desc, qty, unit, *CATALOG[desc]) for desc, qty, unit in items]
