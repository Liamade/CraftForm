# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  commands/server.py                                   ║
# ║  Handles all /server slash command interactions.                             ║
# ║                                                                              ║
# ║  THE SPINE: every command works off one record, a json blob in SSM keyed by  ║
# ║  the server's NAME: /craftform/regions/{region}/servers/{name}               ║
# ║  Only CREATE + SAVE ever go async to CodeBuild (they bake an AMI).           ║
# ║  Everything else finishes IN this Lambda (SSM reads + fast boto3 calls).     ║
# ║                                                                              ║
# ║  Only CREATE/SAVE + the bake recipe ever know a "type"                       ║
# ║  (vanilla|modpack|custom). Everything else is type-blind, so adding          ║
# ║  modpack/custom later is additive, not a refactor.                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import re
from services import ssm, codebuild
import regions  # the catalog -- regions.label(code) for the friendly name
import responses

# separate project from craftform-region: different IAM, and a bake shouldn't queue
# behind a terraform run. hardcoded in the operations lambda's IAM policy too :)
SERVER_PROJECT = "craftform-server"

# the name IS the ssm path, so it only gets characters a path survives
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")

# shape check only -- whether mojang HAS the version is the build's problem
VERSION_PATTERN = re.compile(r"^(latest|\d+\.\d+(\.\d+)?)$")

# friendly size -> what we actually launch
SIZES = {
    "small":  "t3.small",
    "medium": "t3.medium",
    "large":  "t3.large",
}

# ==========================================================================================
#                                   /SERVER COMMAND
# ==========================================================================================
def handle(subcommand, options, body):

    # ===============================<START>================================
    # ROLE: fast toggler. Finishes in this Lambda (sub-second, no defer, no Actions).
    #   read   record(server_id) -> ami_id + world bucket/prefix
    #   do     run_instances from the baked ami_id; boot script pulls the world
    #          from S3 and starts the server (world is NEVER baked into the AMI)
    #   write  record.state = running, instance_id
    if subcommand == "start":
        pass

    # ================================<STOP>=================================
    # ROLE: fast toggler. Finishes in this Lambda. World persists in S3; EC2 goes away.
    #   do     ensure the world is synced up to S3, then terminate/stop the instance
    #   write  record.state = stopped, clear instance_id
    elif subcommand == "stop":
        pass

    # ===============================<CREATE>================================
    # ROLE: the heavy/async one. this lambda does ONLY the cheap part, then hands off to codebuild
    elif subcommand == "create":

        variant, args = create_args(options)

        # -------------------------------<VANILLA>-------------------------------
        if variant == "vanilla":
            # autocomplete SUGGESTS, it doesn't RESTRICT -- discord still lets people
            # ignore the list and type whatever they like, so check it for real
            region = args.get("region", "")

            if region not in ssm.list_names_under("/craftform/regions/"):
                return responses.plain_message(
                    f"`{region}` isn't a deployed region — run `/region list` to see what's available."
                )

            return responses.modal(
                f"server:form:{variant}:{region}",
                f"New {variant} server in {region}",
                [
                    {
                        "custom_id":   "name",
                        "label":       "Server name",
                        "placeholder": "letters, numbers, - _ . (3-32 chars)",
                    },
                    {
                        "custom_id":   "mc_version",
                        "label":       "Minecraft version",
                        "placeholder": "latest",
                        "value":       "latest",
                    },
                    {
                        "custom_id":   "size",
                        "label":       "Size",
                        "placeholder": "small | medium | large",
                        "value":       "small",
                    },
                ],
            )

        # -------------------------------<MODPACK>-------------------------------
        elif variant == "modpack":
            pass
            # FUTURE. args: mrpack_url

        # -------------------------------<CUSTOM>--------------------------------
        elif variant == "custom":
            pass
            # FUTURE. args: loader, mc_version

    # =========================<CREATE :: THE MODAL SUBMIT>=========================
    # api gateway is synchronous, so returning the deferred response ENDS this invocation.
    # everything has to happen before that return :)
    elif subcommand and subcommand.startswith("form:"):
        _, variant, region = subcommand.split(":")
        fields = responses.modal_values(body)

        name       = fields["name"].strip()
        mc_version = fields["mc_version"].strip().lower()
        size       = fields["size"].strip().lower()

        if not NAME_PATTERN.match(name):
            return responses.plain_message(
                f"`{name}` won't work as a name — stick to letters, numbers, `-`, `_` and `.` (3–32 characters)."
            )

        if size not in SIZES:
            return responses.plain_message(f"`{size}` isn't a size I know — pick `small`, `medium`, or `large`.")

        if not VERSION_PATTERN.match(mc_version):
            return responses.plain_message(f"`{mc_version}` isn't a version I recognise — try `latest` or something like `1.21.1`.")

        bucket = ssm.region_config(region)["bucket_name"]

        record = build_record(
            name         = name,
            owner        = body.get("member", body).get("user", {}).get("id"),
            guild        = body.get("guild_id"),
            region       = region,
            server_type  = variant,
            spec         = {"mc_version": mc_version},  # may be "latest" -- the build makes it concrete
            instance_type= SIZES[size],
            bucket       = bucket,
            prefix       = f"servers/{name}/",
        )

        # write FIRST -- overwrite=False is the name guard, so two people racing the
        # same name can't both win
        path = f"/craftform/regions/{region}/servers/{name}"
        if not ssm.put_dict(path, record, overwrite=False):
            return responses.plain_message(f"There's already a server called `{name}` in {region} :(")

        queued = codebuild.start_build(SERVER_PROJECT, {
            "SERVER_NAME":    name,
            "DEPLOY_REGION":  region,
            "MC_VERSION":     mc_version,
            "INSTANCE_TYPE":  SIZES[size],
            "DISCORD_APP_ID": body["application_id"],
            "DISCORD_TOKEN":  body["token"],   # interaction token, NOT the bot token
        })

        if not queued:
            # don't leave a ghost record stuck on "baking" for a build that never ran
            ssm.delete_parameter(path)
            return responses.plain_message("Couldn't kick off the server build :(")

        # tell discord we're thinking -- the build will tell them how it went :)
        return responses.deferred()

    # ===============================<DELETE>================================
    # ROLE: mutator with teeth. Finishes in this Lambda.
    #   CAUTION: AMIs can be SHARED via dedup. Only delete the ami_id if NO other record
    #            references it (refcount) -- otherwise you kill a template still in use.
    #   do     remove the record; remove the world data from S3 (confirm with user first?);
    #          delete the AMI only when it's unreferenced.
    elif subcommand == "delete":
        pass

    # ================================<LIST>=================================
    # ROLE: reader. Type-blind. Finishes in this Lambda.
    #   read   record.list(), optionally filtered by region / owner-guild
    #   do     project each to a short summary line (name, region, state)
    elif subcommand == "list":
        pass

    # ===============================<STATUS>================================
    # ROLE: reader. Finishes in this Lambda.
    #   read   record.get(server_id) -> state
    #   do     if running, pull the live public IP from the instance and surface it
    elif subcommand == "status":
        pass

    # ===============================<MODIFY>================================
    # ROLE: mutator. FORKS by what's being changed:
    #   cheap  -> instance size: just a future launch param. NO rebake. Finishes in Lambda.
    #   spec   -> version / loader / mods: a DIFFERENT hash = a rebake = create in disguise
    #             (async -> Actions). v1: REJECT spec changes with "make a new server" until
    #             the rebake path exists. Only allow the cheap changes for now.
    elif subcommand == "modify":
        pass

    # ================================<SAVE>=================================
    # ROLE: mutator + data stakes. ASYNC -- this is a bake too, so it DEFERS + dispatches
    #       just like create (not a quick in-Lambda op).
    #   guard  running servers only
    #   do     flush the world (save-all flush bracketing), then create-image from the live
    #          instance -> a NEW template. This is the custom-build "save my mods" loop.
    #   NOTE   the result is a hand-modified snapshot with no declared spec -> NOT deduped;
    #          every save produces its own unique template.
    elif subcommand == "save":
        pass

    # =================================<GET>==================================
    # ROLE: reader. Finishes in this Lambda.
    #   read   record.get(server_id) -> full detail
    #   do     surface everything, incl. the pack link for modded servers so players can
    #          install the matching mods client-side (server IP alone won't let them join).
    elif subcommand == "get":
        pass

    # ===============================<UNKNOWN>==============================
    else:
        return responses.plain_message(f"Unknown /server subcommand: `{subcommand}`. :(")


# ==========================================================================================
#                                  BUILD A SERVER RECORD
# ==========================================================================================
# the shape of every server blob in one place. keyword-only on purpose -- these are nearly
# all strings, and a positional swap of region/state/type would sail straight past you :)
# the None fields get filled in by the build, so a half-built record still reads fine
# ------------------------------------------------------------------------------------------
def build_record(*, name, owner, guild, region, server_type, spec, instance_type, bucket, prefix):
    return {
        "name":          name,
        "owner":         owner,          # discord user id of whoever ran the command
        "guild":         guild,          # for /list filtering
        "region":        region,
        "type":          server_type,    # vanilla | modpack | custom
        "spec":          spec,           # what gets hashed for ami reuse
        "instance_type": instance_type,  # a launch param -- no rebake to resize
        "bucket":        bucket,
        "prefix":        prefix,
        "state":         "baking",
        "ami_id":        None,           # v-- filled in by the build --v
        "spec_hash":     None,
        "instance_id":   None,
    }


# ==========================================================================================
#                            DIG THE CREATE ARGS OUT
# ==========================================================================================
# create is a subcommand GROUP, so what the user typed sits two layers down:
#   options[0]["options"][0]  = the variant, and ITS options are the args
# ------------------------------------------------------------------------------------------
def create_args(options):
    # walk down the options tree to the variant and its args
    variant_option = options[0]["options"][0]
    args = {option["name"]: option.get("value") for option in variant_option.get("options", [])}
    return variant_option["name"], args


# ==========================================================================================
#                                    AUTOCOMPLETE
# ==========================================================================================
# fires on EVERY keystroke, so keep it to one ssm list and out. blowing the 3s here just
# stops suggestions appearing rather than erroring visibly.
#
# variant-blind on purpose -- vanilla/modpack/custom all get region suggestions from the
# same branch, so a new variant needs the option REGISTERED, not code in here :)
# ------------------------------------------------------------------------------------------
def autocomplete(options, body):

    # gets the focused option (the one the cursor is actually in)
    focused = focused_option(options)

    # only offer region suggestions when the user is actually typing in the region field
    if focused and focused["name"] == "region":
        # get the currently typed value
        typed = (focused.get("value") or "").lower()

        # filter the DEPLOYED (ones in ssm) regions to those matching what's been typed so far.
        # match on the CODE or the friendly name, so "us-east" and "virginia" both land :)
        deployed = [
            code for code in ssm.list_names_under("/craftform/regions/")
            if typed in code.lower() or typed in regions.label(code).lower()
        ]

        # show the friendly name, SEND the code -- discord hands `value` back, not `name`.
        # same "Name · code" shape /region list uses, so the two commands read alike
        return responses.autocomplete(
            [{"name": f"{regions.label(code)}  ·  {code}", "value": code} for code in sorted(deployed)[:25]]
        )

    # return nothing if the focused option isn't the region one
    return responses.autocomplete([])


# =================================FIND THE FOCUSED OPTION==================================
# walk down until we hit the option the cursor is actually in. recursive because the depth
# changes with the command shape -- /server start sits one layer up from /server create
# vanilla, and only discord knows which we're looking at
# ------------------------------------------------------------------------------------------
def focused_option(options):
    # walk down the options tree until we find the one the cursor is actually in
    for option in options:
        if option.get("focused"):
            return option
        # if the option has nested options, keep going down until we find the focused one
        nested = focused_option(option.get("options", []))
        
        # if focused option found in nested option list, just return
        if nested:
            return nested

    return None