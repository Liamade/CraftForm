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
#                            MAIN LAMBDA FUNCTION ENTRY POINT
# ==========================================================================================


def handler(event, context):

    # ===============================RE-REGISTER COMMANDS ON UPDATE===============================
    # when someone runs /update, the staging function invokes this lambda to re-register commands
    if event.get("action") == "register_commands":
        # SET UP CLIENTS
        secrets_manager = boto3.client("secretsmanager")  # need the bot token to talk to discord
        secrets = secrets_manager.get_secret_value(SecretId="craftform-secrets")
        secrets_dict = json.loads(secrets["SecretString"])  # secret value is a JSON string

        # DISCORD VARIABLES AND CLIENT
        discord_app_id = os.environ["DiscordAppId"]  # injected as an env var on this function already
        discord_bot_token = secrets_dict["Discord-Bot-Token"]  # grab the bot token out of it
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

    http = urllib3.PoolManager()  # create a new HTTP connection pool manager to make HTTP requests | have to initalize outside the try statement so it can send Cloudformation responses in case of errors

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
            # ==================================INITIALIZATION=================================

            ssm = boto3.client("ssm")  # create a AWS System Manager client to interact with SSM Parameter Store
            secrets_manager = boto3.client("secretsmanager")  # create a AWS Secrets Manager client to interact with Secrets Manager
            secrets = secrets_manager.get_secret_value(
                SecretId="craftform-secrets"
            )  # get the secret value for the secret named "craftform-secrets" from Secrets Manager
            
            
            secrets_dict = json.loads(secrets["SecretString"])  # the secret value is a JSON string

            # ================================GITHUB INTEGRATION===============================
            github_pat = secrets_dict["Github-PAT"]  # get the GitHub Personal Access Token from the secrets dictionary

            github_client = GithubClient(github_pat, github_username)

            github_client.fork_repo()  # fork the CraftForm repo into the user's GitHub account and wait for the fork to be ready

            github_client.enable_actions()  # enable GitHub Actions in the forked repo

            github_client.push_variables(github_var_dict)  # push all the repo variables :)

            github_client.push_secrets(github_secret_dict)  # push the encrypted secrets to the forked GitHub repo

            # store the GitHub forked repo URL into SSM parameter store
            ssm.put_parameter(
                Name="/craftform/config/github/repo",
                Value=f"{github_username}/CraftForm",
                Type="String",
                Overwrite=True,
            )

            # =================================DISCORD INTEGRATION=============================
            # get the bot token secret
            discord_bot_token = secrets_dict["Discord-Bot-Token"]  # get the bot token from Secret Manager

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
