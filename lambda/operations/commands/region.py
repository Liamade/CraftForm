# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  commands/region.py                                   ║
# ║  Handles all /region slash command interactions.                             ║
# ║  Create, delete, and list regions.                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import json
from services import ssm, s3, codebuild  # service helpers
import regions  # the catalog -- regions.SUPPORTED (codes) + regions.label(code)
import responses  # discord interaction-response builders

# the prefix every deployed region's config lives under
REGIONS_PREFIX = "/craftform/regions/"

# the codebuild project that actually runs terraform for regions -- this replaced the old github
# actions workflow. the operations lambda's IAM policy allows codebuild:StartBuild on craftform-*,
# so this has to keep that prefix. servers get their own project, hence the -region suffix
REGION_PROJECT = "craftform-region"

# ==========================================================================================
#                                   /REGION COMMAND
# ==========================================================================================
def handle(subcommand, options, body):

    # ================================<CREATE>================================
    if subcommand == "create":
        # which regions are already deployed
        active_regions = ssm.list_names_under(REGIONS_PREFIX)

        # offer everything in the catalog that isn't already deployed
        available_regions = regions.SUPPORTED - set(active_regions)

        # every supported region is already live -- nothing left to spin up
        if not available_regions:
            return responses.plain_message("Every supported region is already deployed — nothing left to create.")

        # build the dropdown options -- map each raw region code to its friendly label
        options = [{"label": regions.label(r), "value": r} for r in sorted(available_regions)]

        # return the packet
        return responses.drop_down("Pick a region to deploy into:", "region:apply_create", "Choose a region...", options)


    # ================================<DELETE>================================
    if subcommand == "delete":
        # which regions are already deployed
        active_regions = ssm.list_names_under(REGIONS_PREFIX)

        # nothing deployed -- nothing to tear down
        if not active_regions:
            return responses.plain_message("No regions are deployed yet — there's nothing to destroy.")

        # build the dropdown options -- map each raw region code to its friendly label
        options = [{"label": regions.label(r), "value": r} for r in sorted(active_regions)]

        # return the response packet
        return responses.drop_down("Pick a region to destroy:", "region:apply_destroy", "Choose a region...", options)

    # =================================<LIST>=================================
    if subcommand == "list":
        # hand the fleet over to the embed builder and ship it
        return region_atlas(ssm.list_names_under(REGIONS_PREFIX))

    # =================================<APPLY>=================================
    if subcommand.startswith("apply"):
        # capture the action that is going to apply
        action = subcommand.split('_')[1]

        # capture the region
        region = body["data"]["values"][0]

        if action == "destroy":

            # guard the destroy -- if the region's s3 bucket still has objects in it
            bucket = ssm.region_config(region)["bucket_name"]
            
            if s3.bucket_has_objects(bucket):
                return responses.plain_message(
                    f"**{regions.label(region)}** still has world data stored in its S3 bucket "
                    f"(`{bucket}`), so I can't tear the region down yet :( \n\n"
                    "Please delete the objects in that bucket first, then run `/region delete` again. :)"
                )


        # kick off the terraform build. nothing's been written yet, so there's no rollback here
        queued = codebuild.start_build(REGION_PROJECT, {
            "DEPLOY_REGION":  region,                  # the region we're building INTO
            "TF_ACTION":      action,                  # create or destroy
            "DISCORD_APP_ID": body["application_id"],
            "DISCORD_TOKEN":  body["token"],           # interaction token, NOT the bot token
        })

        # the function returns false if the build didn't queue 
        if not queued:
            return responses.plain_message("Couldn't kick off the terraform build :(")

        # tell discord we're thinking - the build will tell discord what happened :)
        return responses.deferred()



# ==========================================================================================
#                                 REGION ATLAS (LIST)
# ==========================================================================================
def region_atlas(active_regions):
    # no regions yet -- give them a friendly nudge instead of an empty void
    if not active_regions:
        embed = {
            "title": "« CraftForm Atlas »",
            "description": (
                "```\n"
                "  no regions forged yet  \n"
                "```\n"
                "The map is yours to draw — run `/region create` to plant the first flag."
            ),
            "color": 0xFEE75C,  # warm yellow -- nothing's wrong, just waiting
        }
    # otherwise lay out every region CraftForm calls home
    else:
        embed = {
            "title": "« CraftForm Atlas »",
            "description": (
                "Every corner of the world under CraftForm's banner:\n\n"
                + "\n".join(
                    f"▪  {regions.label(region)}  ·  `{region}`"
                    for region in sorted(active_regions)
                )
            ),
            "color": 0x57F287,  # discord green -- alive and well
            "footer": {
                "text": f"{len(active_regions)} region(s) standing tall"
            },
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "type": 4,
            "data": {
                "flags": 64,  # only visible to the user who ran the command
                "embeds": [embed],
            }
        })
    }