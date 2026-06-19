"""Central configuration paths for the Kaufland receipts pipeline."""
from pathlib import Path

# Root folder of the downloaded receipts, organised per store in subfolders:
#   <RECEIPTS_DIR>/Kaufland/*.pdf   and   <RECEIPTS_DIR>/Lidl/*.png
# Override with the RECEIPTS_DIR env var if the path changes.
import os

RECEIPTS_DIR = Path(
    os.environ.get("RECEIPTS_DIR", r"C:\Users\s.demirov\My Drive\DigitalReceipts")
)

# Project-local data directory (kept out of Google Drive).
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "receipts.db"
MAPPING_CSV = DATA_DIR / "product_mapping.csv"
PRODUCT_META_CSV = DATA_DIR / "product_meta.csv"  # editable brand/category per product
UNPARSED_LOG = DATA_DIR / "unparsed_lines.log"

# rapidfuzz similarity threshold (0-100) for grouping product name variants.
FUZZY_THRESHOLD = 88

# Bulgaria adopted the euro on 2026-01-01. All amounts are stored & shown in EUR;
# pre-2026 BGN receipts are converted at the fixed rate 1 EUR = 1.9558 BGN.
BGN_PER_EUR = 1.9558
