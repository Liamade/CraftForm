# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  regions.py                                           ║
# ║  The catalog of regions CraftForm is willing to deploy into.                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                                  REGION CATALOG
# ==========================================================================================
# this helps build the dictionary of supported regions and their friendly labels. based on
# the catalog file "regions.json" in this directory
# ------------------------------------------------------------------------------------------
import json
import os

# captures the path to the catalog file based on this file's location
_CATALOG = os.path.join(os.path.dirname(__file__), "regions.json")

# capture the catalog into a dict for easy lookups by region code
with open(_CATALOG, encoding="utf-8") as catalog:
    NAMES = json.load(catalog)  # {"us-east-1": "US East (N. Virginia)", ...}

# just the codes -- a set so callers can & / - against it directly instead of looping
SUPPORTED = set(NAMES)


# =====================================FRIENDLY LABEL====================================
# get the pretty name for the region code, or just return the code if it's not already
# in the catalog (shouldn't happen but like yaknow a lot of things that shouldn't happen do)
def label(code):
    return NAMES.get(code, code)
