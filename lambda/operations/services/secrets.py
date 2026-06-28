# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  services/secrets.py                                  ║
# ║  Little shared helper for pulling fields out of the craftform secret bundle. ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                               SECRETS MANAGER HELPERS
# ==========================================================================================
# everything in this lambda reads from the same "craftform-secrets" bundle  this centralizes 
# the secret id and the fetch+parse so the command files stay clean
# ------------------------------------------------------------------------------------------
import json
from aws_clients import secrets  # shared client -- made once per cold start

# the one secret bundle this whole lambda reads from
_SECRET_ID = "craftform-secrets"


# ======================================GET SECRET======================================
# fetched fresh every call ON PURPOSE -- secrets can rotate, so we don't cache it :)
def get_secret(name):
    secret_dict = json.loads(secrets.get_secret_value(SecretId=_SECRET_ID)["SecretString"])

    try:
        return secret_dict[name]
    except KeyError:
        print(f"Secret not found for {name} :(")
        raise  # re-raise so we fail loud instead of handing back a silent None
