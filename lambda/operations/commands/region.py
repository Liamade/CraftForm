# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  commands/region.py                                   ║
# ║  Handles all /region slash command interactions.                             ║
# ║  Create, delete, and list regions.                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import json
from aws_clients import ec2, codebuild  # raw clients we still call directly
from services import ssm, s3  # service helpers
import responses  # discord interaction-response builders

# the prefix every deployed region's config lives under
REGIONS_PREFIX = "/craftform/regions/"

# the codebuild project that actually runs terraform for regions -- this replaced the old github
# actions workflow. the operations lambda's IAM policy allows codebuild:StartBuild on craftform-*,
# so this has to keep that prefix. servers get their own project, hence the -region suffix
REGION_PROJECT = "craftform-region"

# the regions CraftForm is willing to deploy into 
REGION_NAMES = {
    "us-east-1":      "US East (N. Virginia)",
    "us-east-2":      "US East (Ohio)",
    "us-west-1":      "US West (N. California)",
    "us-west-2":      "US West (Oregon)",
    "ca-central-1":   "Canada (Central)",
    "sa-east-1":      "South America (São Paulo)",
    "eu-west-1":      "Europe (Ireland)",
    "eu-west-2":      "Europe (London)",
    "eu-west-3":      "Europe (Paris)",
    "eu-central-1":   "Europe (Frankfurt)",
    "eu-north-1":     "Europe (Stockholm)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-south-1":     "Asia Pacific (Mumbai)",
}

# the set of codes we support -- derived from the names map so the two never drift
SUPPORTED_REGIONS = set(REGION_NAMES)

# ==========================================================================================
#                                   /REGION COMMAND
# ==========================================================================================
def handle(subcommand, options, body):

    # ================================<CREATE>================================
    if subcommand == "create":
        # which regions are already deployed
        active_regions = ssm.list_names_under(REGIONS_PREFIX)

        # the regions aws actually offers right now
        all_regions = {region["RegionName"] for region in ec2.describe_regions(AllRegions=True)["Regions"]}

        # offer only supported regions that aws has AND aren't already deployed
        available_regions = (all_regions & SUPPORTED_REGIONS) - set(active_regions)

        # every supported region is already live -- nothing left to spin up
        if not available_regions:
            return responses.plain_message("Every supported region is already deployed — nothing left to create.")

        # build the dropdown options -- map each raw region code to its friendly label
        options = [{"label": REGION_NAMES.get(r, r), "value": r} for r in sorted(available_regions)]

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
        options = [{"label": REGION_NAMES.get(r, r), "value": r} for r in sorted(active_regions)]

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

        # ---- guard: can't tear a region down while its world-data bucket still has objects ----
        if action == "destroy":
            bucket = ssm.get_dict(f"/craftform/regions/{region}/config")["bucket_name"]
            if s3.bucket_has_objects(bucket):
                return responses.plain_message(
                    f"**{REGION_NAMES.get(region, region)}** still has world data stored in its S3 bucket "
                    f"(`{bucket}`), so I can't tear the region down yet.\n\n"
                    "Please delete the objects in that bucket first, then run `/region delete` again. :)"
                )

        # kick off the terraform build. the region + action tell it WHAT to do, and the
        # discord pair lets the build edit this exact "thinking..." message when it finishes.
        # fire-and-forget on purpose -- we've got 3 seconds to answer discord, the build takes minutes.
        # these names have to line up with what buildspec.yaml reads, so don't rename one alone :)
        try:
            codebuild.start_build(
                projectName=REGION_PROJECT,
                environmentVariablesOverride=[
                    {"name": "DEPLOY_REGION", "value": region},                   # the region we're building INTO
                    {"name": "TF_ACTION", "value": action},                       # create or destroy
                    {"name": "DISCORD_APP_ID", "value": body["application_id"]},
                    {"name": "DISCORD_TOKEN", "value": body["token"]},            # interaction token, NOT the bot token
                ],
            )
        except Exception as e:
            print(f"Failed to start the terraform build: {e} :(")
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
                    f"▪  {REGION_NAMES.get(region, region)}  ·  `{region}`"
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