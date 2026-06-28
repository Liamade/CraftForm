# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  commands/update.py                                   ║
# ║  Handles the /update slash command.                                          ║
# ║  Kicks off the staging function to sync, redeploy, and refresh commands.     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

import json

from aws_clients import lambda_client  # shared client -- no need to build our own
import responses  # discord interaction-response builders -- responses.deferred(), etc.


# ==========================================================================================
#                                   /UPDATE COMMAND
# ==========================================================================================
def handle(subcommand, options, body):

    # ======================INVOKE STAGING FUNCTION=======================
    lambda_client.invoke(
        FunctionName="craftform-staging-function",  # staging function does all the actual heavy lifting
        InvocationType="Event",  # fire-and-forget - returns immediately, we don't wait on it
        Payload=json.dumps(
            {
                "action": "update",  # tells staging to take the /update path, not the cloudformation one
                "application_id": body["application_id"],  # staging needs this because it isn't used in the stage code lambda before this
                "interaction_token": body["token"],  # the token for THIS interaction - lets us tell discord which channel or guild the message is going to
            }
        ).encode(),
    )

    # ===========================DISCORD RESPONSE===========================
    # tell discord we're thinking - staging lambda will edit this message when it's done :)
    return responses.deferred()
