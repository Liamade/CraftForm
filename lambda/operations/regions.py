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
    NAMES = json.load(catalog)  # establish a dictionary from the json

# get just the codes
SUPPORTED = set(NAMES)

# =====================================FRIENDLY LABEL====================================
# get the pretty name for the region code, or just return the code if it's not already
# in the catalog (shouldn't happen but like yaknow a lot of things that shouldn't happen do)
def label(code):
    return NAMES.get(code, code)


# =====================================RESOLVE A REGION==================================
# label() backwards -- friendly name in, region code out.
def resolve(text):

    # `or ""` so a None gets handled here instead of blowing up on .strip()
    text = (text or "").strip().lower()

    if not text:
        return None

    # if already a code send back the code
    if text in NAMES:
        return text

    # check the catalog to get the region code
    for code, name in NAMES.items():
        if name.lower() == text:
            return code

    # if nothing worked :(
    return None

    
