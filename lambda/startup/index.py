# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                              CraftForm                                       ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  STARTUP LAMBDA  ::  index.py                                                ║
# ║  Entry point for the CloudFormation Custom Resource startup function.        ║
# ║  Orchestrates GitHub and Discord setup on first deployment.                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


# ==========================================================================================
#                            IMPORTS AND DEPENDENCIES
# ==========================================================================================
import urllib3
import json
import boto3
import os  # for accessing environment variables injected into the Lambda
from discord_api import DiscordClient # import the discord client class from discord_api
from github_api import GithubClient # import the class from github_api

# ==========================================================================================
#                            SECRETS
# ==========================================================================================
# client lives at module scope so warm invocations reuse the same connection (AWS best practice).
# the secrets (Discord bot token + GitHub PAT) are fetched at runtime and never stored in the
# function's env vars, so they don't show up in the Lambda config.
secrets_manager = boto3.client("secretsmanager")


def get_secrets():
    """Fetch and parse the craftform-secrets bundle from Secrets Manager."""
    secret = secrets_manager.get_secret_value(SecretId="craftform-secrets")
    return json.loads(secret["SecretString"])  # secret value is a JSON string


# ==========================================================================================
#                            MAIN LAMBDA FUNCTION ENTRY POINT
# ==========================================================================================


def handler(event, context):

    # ===============================RE-REGISTER COMMANDS ON UPDATE===============================
    # when someone runs /update, the staging function invokes this lambda to re-register commands
    if event.get("action") == "register_commands":

        # DISCORD VARIABLES AND CLIENT -- app id is injected as an env var, bot token comes from Secrets Manager
        discord_app_id = os.environ["DiscordAppId"]
        discord_bot_token = get_secrets()["Discord-Bot-Token"]
        discord_client = DiscordClient(discord_bot_token, discord_app_id)

        # RUN
        try:
            discord_client.register_commands()  # registers whatever is in slash_commands now

        # ON FAILURE - this path ISN'T cloudformation, so there's no ResponseURL or StackId to hand back.
        except Exception as e:
            print(f"Failed to re-register commands: {e}")
            raise


        # ON SUCCESS
        return {"status": "commands registered :)"}  # staging only tells the user "done" once this comes back clean



    # ========================================STARTUP PATH========================================

    http = urllib3.PoolManager()  # init outside the try so the except/response path below can still reach it

    try:  # wrapping entire function in a try catch block because it makes it catches errors and also ensures when deleting cloudformation state, it deletes early

        # RUN -- make sure the startup script doesn't run on deletion
        if event["RequestType"] != "Delete": 
            # ===============================INJECTED VARIABLES===============================

            aws_api_url = os.environ["ApiGatewayUrl"]
            github_username = os.environ["GithubUsername"]
            discord_app_id = os.environ["DiscordAppId"]

            # build a dictionary of the variables being passed into github
            github_var_dict = {
                "HOME_REGION": os.environ["Region"],
                "STATE_BUCKET": os.environ["HomeBucket"],
            }
            github_secret_dict = {
                "AWS_ROLE_ARN": os.environ["GithubActionsRoleArn"]
            }

            # pull the secrets bundle once; reused by both the GitHub and Discord integrations below
            secrets = get_secrets()

            # ================================GITHUB INTEGRATION===============================
            github_pat = secrets["Github-PAT"]  # GitHub Personal Access Token from Secrets Manager

            github_client = GithubClient(github_pat, github_username)

            github_client.fork_repo()  # fork the CraftForm repo into the user's GitHub account and wait for the fork to be ready

            github_client.enable_actions()  # enable GitHub Actions in the forked repo

            github_client.push_variables(github_var_dict)  # push all the repo variables :)

            github_client.push_secrets(github_secret_dict)  # push the encrypted secrets to the forked GitHub repo
            # NOTE: the /craftform/config/github/repo SSM param is now declared statically in home-region.yaml

            # =================================DISCORD INTEGRATION=============================
            # get the bot token secret
            discord_bot_token = secrets["Discord-Bot-Token"]  # bot token from Secrets Manager

            # set up discord client
            discord_client = DiscordClient(discord_bot_token, discord_app_id)
            
            discord_client.send_api_url(aws_api_url) # set the API Gateway URL as the interactions endpoint in the Discord

            discord_client.register_commands()  # register the slash commands with the Discord API



        # =================================SUCCESS RESPONSE=============================
        response = {
            "Status": "SUCCESS",
            "PhysicalResourceId": "craftform-startup",
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
        }

    # ====================================ERROR HANDLING================================
    # if any errors or failures happen - report to cloudformation with failure status and error message
    except Exception as e:
        response = {
            "Status": "FAILED",
            "Reason": str(e),
            "PhysicalResourceId": "craftform-startup",
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
        }

    # =============================CLOUDFORMATION RESPONSE=============================

    http.request(  # make an HTTP request to CloudFormation to report the end status
        "PUT",
        event["ResponseURL"],  # cloudformation response URL is given in the event object when the Lambda is invoked by CloudFormation
        body=json.dumps(response),  # one of the "2" status responses defined above - success or failure
        headers={"Content-Type": "application/json"},
    )
