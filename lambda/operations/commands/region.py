# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  commands/region.py                                   ║
# ║  Handles all /region slash command interactions.                             ║
# ║  Create, delete, and list regions.                                           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import urllib3
import json
from aws_clients import secrets, ssm, ec2
from ssm_helpers import list_names_under  # shared ssm helpers

# the prefix every deployed region's config lives under
REGIONS_PREFIX = "/craftform/regions/"

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
        active_regions = list_names_under(REGIONS_PREFIX)

        # the regions aws actually offers right now
        all_regions = {region["RegionName"] for region in ec2.describe_regions(AllRegions=True)["Regions"]}

        # offer only supported regions that aws has AND aren't already deployed
        available_regions = (all_regions & SUPPORTED_REGIONS) - set(active_regions)

        # every supported region is already live -- nothing left to spin up
        if not available_regions:
            return plain_message("Every supported region is already deployed — nothing left to create.")

        # build out the response packet
        content = "Pick a region to deploy into:"
        custom_id = "region:apply_create"
        placeholder = "Choose a region..."

        # return the packet
        return drop_down(content, custom_id, placeholder, available_regions)


    # ================================<DELETE>================================
    if subcommand == "delete":
        # which regions are already deployed
        active_regions = list_names_under(REGIONS_PREFIX)

        # nothing deployed -- nothing to tear down
        if not active_regions:
            return plain_message("No regions are deployed yet — there's nothing to destroy.")

        # build out the response packet
        content = "Pick a region to destroy:"
        custom_id = "region:apply_destroy"
        placeholder = "Choose a region..."

        # return the response packet
        return drop_down(content, custom_id, placeholder, active_regions)

    # =================================<LIST>=================================
    if subcommand == "list":
        # hand the fleet over to the embed builder and ship it
        return region_atlas(list_names_under(REGIONS_PREFIX))

    # =================================<APPLY>=================================
    if subcommand.startswith("apply"):
        # capture the action that is going to apply
        action = subcommand.split('_')[1]

        # capture the region
        region = body["data"]["values"][0]

        # get the github pat from the secret manager
        secret = secrets.get_secret_value(
                SecretId="craftform-secrets"
            )  # get the secret value for the secret named "craftform-secrets" from Secrets Manager
            
        secrets_dict = json.loads(secret["SecretString"])

        github_pat = secrets_dict["Github-PAT"]
        
        # get the github repo
        github_repo = ssm.get_parameter(Name="/craftform/config/github/repo")["Parameter"]["Value"]


        # trigger the github actions workflow
        http = urllib3.PoolManager()
        githubRequest = http.request(
            "POST",
            f"https://api.github.com/repos/{github_repo}/actions/workflows/tf-deploy-region.yaml/dispatches",
            body=json.dumps({
                "ref": "main",
                "inputs": {
                    "region": region,
                    "action": action,
                    "application_id": body["application_id"],
                    "interaction_token": body["token"]
                }
            }).encode(),
            headers={
                "Authorization": f"Bearer {github_pat}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.github+json"
            }
        )

        # check and see if the http request went through
        if githubRequest.status != 204:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "type": 4,  # respond immediately to the user
                        "data": {
                            "content": "Github Connection failed :(",
                            "flags": 64  # only visible to the user who ran the command
                        },
                    }
                ),
            }

        # tell discord we're thinking - terraform workflow will tell discord what happened :)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"type": 5}),  # type 5 = deferred response = "thinking..." spinner
        }

# ==========================================================================================
#                                 DROP DOWN RESPONSE
# ==========================================================================================
def drop_down (content, custom_id, placeholder, options):
    return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "type": 4,
                "data": {
                    "content": content,
                    "flags": 64,  # only visible to the user who ran the command
                    "components": [
                        {
                            "type": 1,  # type 1 = action row (container for components)
                            "components": [
                                {
                                    "type": 3,  # string select menu
                                    "custom_id": custom_id,
                                    "placeholder": placeholder,
                                    "options": [
                                        # label = friendly name the user sees, value = raw aws code we act on
                                        {"label": REGION_NAMES.get(r, r), "value": r}
                                        for r in sorted(options)
                                    ]
                                }
                            ]
                        }
                    ]
                }
            })
        }

# ==========================================================================================
#                                 PLAIN MESSAGE RESPONSE
# ==========================================================================================
def plain_message(text):
    # a simple ephemeral text reply -- used when there's nothing to show in a menu
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "type": 4,
            "data": {
                "content": text,
                "flags": 64,  # only visible to the user who ran the command
            }
        })
    }

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