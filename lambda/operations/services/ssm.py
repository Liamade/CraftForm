# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  services/ssm.py                                      ║
# ║  Little shared helpers for poking around the SSM parameter store.            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                               SSM PARAMETER HELPERS
# ==========================================================================================
# almost all of the command code uses the ssm parameter store the same way and the tree
# is built in a way that listing it is relatively easy. this acts as a shared helper to help
# minimize the code in other files
# ------------------------------------------------------------------------------------------
import json
from aws_clients import ssm  # shared client -- made once per cold start


# ===============================LIST NAMES UNDER A PREFIX===============================
# pull the resource names sitting directly under a prefix.
def list_names_under(prefix):

    # make sure we've got the trailing slash so the strip + split below lines up
    if not prefix.endswith("/"):
        prefix += "/"

    names = []

    # paginate -- get_parameters_by_path caps at 10 results a page, so we have to loop
    paginator = ssm.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(Path=prefix, Recursive=True):
        for param in page["Parameters"]:
            # chop the prefix off, then take the FIRST segment after it = the resource name
            name = param["Name"][len(prefix):].split("/")[0]
            if name and name not in names:  # dedupe -- multiple params per resource is fine
                names.append(name)

    return names

# =====================================GET A VARIABLE====================================
def get_parameter(name):
    return ssm.get_parameter(Name=name)["Parameter"]["Value"]

# ====================================GET A JSON DICT====================================
def get_dict(name):
    # turns string blobs in the ssm parameter store into a json dictionary
    return json.loads(ssm.get_parameter(Name=name)["Parameter"]["Value"])


# ===================================GET A REGION CONFIG=================================
# gets the config for the given region, which is just a blob dict with the keys:
#   bucket_name       the world-data bucket for this region
#   security_group    the minecraft SG (25565 open)
#   instance_profile  the role the ec2 servers assume
#   subnet_ids        {az: subnet_id} -- pick one to launch into
def region_config(region):
    return get_dict(f"/craftform/regions/{region}/config")


# ====================================PUT A JSON DICT====================================
# overwrite=False is the CREATE guard -- ssm rejects a name that's already taken, and it's
# atomic, so no check-then-write race. returns True if it wrote, False if the name was
# taken. we swallow the exception because callers import this MODULE, not the raw client :)
def put_dict(name, data, overwrite=True):
    try:
        ssm.put_parameter(
            Name=name,
            Value=json.dumps(data),
            Type="String",
            Overwrite=overwrite,
        )
        return True

    except ssm.exceptions.ParameterAlreadyExists:
        return False  # only reachable with overwrite=False -- the name's in use


# ====================================DELETE A PARAMETER=================================
def delete_parameter(name):
    ssm.delete_parameter(Name=name)


# ============================GET THE DISCORD PUBLIC KEY (cached)============================
# the discord public key never changes, so there's no point hitting ssm on every single
# invocation. we fetch it ONCE per cold start and reuse it on every warm one after that :)
# ------------------------------------------------------------------------------------------
_discord_public_key = None  # starts empty -- nothing fetched yet


def get_discord_public_key():
    global _discord_public_key  # we wanna update the cache var above, not make a new local one

    if _discord_public_key is None:  # first call on this container? go grab it + save it
        _discord_public_key = get_parameter("/craftform/config/discord/public-key")

    return _discord_public_key  # every call after just hands back the saved copy -- no ssm hit
