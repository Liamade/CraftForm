# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  index.py                                             ║
# ║  Handles all incoming Discord interactions for CraftForm.                    ║
# ║  Verifies signatures, answers pings, and routes slash commands.              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                            IMPORTS AND DEPENDENCIES
# ==========================================================================================
import json
import base64
from nacl.signing import VerifyKey  # cryptographic library for verifying signatures

from commands import server, template, region, update  # the actual command handlers
from ssm_helpers import get_discord_public_key  # cached getter -- only hits ssm on cold start


# ==========================================================================================
#                                 DISCORD API INTERACTIONS
# ==========================================================================================
def handler(event, context):

    print("Received event:", json.dumps(event))  # log the incoming event for debugging

    # ====================================VERIFY DISCORD SIGNATURE================================
    
    discord_public_key = get_discord_public_key()  # cached -- only hits ssm on the first (cold start) call

    rawBody = event["body"]  # capture the raw body FIRST - api gateway can mess with it before we verify

    # API Gateway may base64 encode the body when forwarding to Lambda
    if event.get("isBase64Encoded", False):
        rawBody = base64.b64decode(rawBody).decode()  # decode it back to a string if it was encoded

    print("Verifying signature....")
    if not verify_signature(event, rawBody, discord_public_key):
        print("Signature verification FAILED :(")
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Invalid request signature"}),
        }

    print("Signature verification SUCCESS :)")

    body = json.loads(rawBody)  # safe to parse now that the signature is verified

    print("Interaction type:", body["type"])

    # ====================================HANDLE PING================================
    # discord sends a ping when first setting up the interactions endpoint - just gotta say hi back :)
    if body["type"] == 1:
        return {
            "statusCode": 200,
            "body": json.dumps({"type": 1}),  # type 1 = pong
        }

    # ====================================ROUTE SLASH COMMANDS===================================
    if body["type"] == 2:
        command = body["data"]["name"]  # which top-level command was used
        options = body["data"].get("options", [])  # top-level commands like /update have no subcommands, so this can be empty
        subcommand = options[0]["name"] if options else None  # only grab a subcommand if there actually is one

        if command == "server":
            return server.handle(subcommand, options, body)

        if command == "template":
            return template.handle(subcommand, options, body)

        if command == "region":
            return region.handle(subcommand, options, body)

        if command == "update":
            return update.handle(subcommand, options, body)

    # ====================================ROUTE COMPONENT INTERACTIONS===================================
    if body["type"] == 3:
        # this splits the custom_id so i can map it to only one function and lessen the logic
        command, subcommand = body["data"]["custom_id"].split(':')  # command = part[0] | subcommand =part[1]

        if command == "region":
            return region.handle(subcommand, [], body)



# ==========================================================================================
#                    VERIFY DISCORD SIGNATURE AND HANDLE INTERACTIONS
# ==========================================================================================
def verify_signature(event, rawBody, public_key):

    signature = event["headers"]["x-signature-ed25519"]  # get the signature from the request headers
    timestamp = event["headers"]["x-signature-timestamp"]  # get the timestamp from the request headers

    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))  # convert the public key from hex to a PyNaCL VerifyKey object
        verify_key.verify(
            timestamp.encode() + rawBody.encode(), bytes.fromhex(signature)
        )  # combine timestamp and body, then verify the signature against the public key

    except Exception as e:  # catch any exceptions because discord sends a bad ping when first setting up the interactions endpoint
        print("Error occurred while verifying signature:", str(e))
        return False  # signature verification failed :(
    return True

