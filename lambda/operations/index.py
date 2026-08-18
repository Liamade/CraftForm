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

from commands import template, region, update, server  # the actual command handlers
from services import ssm  # ssm helpers -- call as ssm.get_discord_public_key(), ssm.get_parameter(), etc.
import responses  # discord interaction-response builders -- responses.pong(), etc.


# ==========================================================================================
#                                 DISCORD API INTERACTIONS
# ==========================================================================================
def handler(event, context):

    print("Received event:", json.dumps(event))  # log the incoming event for debugging

    # ====================================VERIFY DISCORD SIGNATURE================================
    
    discord_public_key = ssm.get_discord_public_key()  # cached -- only hits ssm on the first (cold start) call

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
        return responses.pong()

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

    # ====================================ROUTE AUTOCOMPLETE===================================
    # type 4 = discord asking what to suggest while the user is still typing. fires on
    # every keystroke, so these handlers stay cheap :)
    if body["type"] == 4:
        command = body["data"]["name"]
        options = body["data"].get("options", [])

        if command == "server":
            return server.autocomplete(options, body)

    # ====================================ROUTE COMPONENTS + MODALS===================================
    # type 3 = clicked a button / picked from a dropdown | type 5 = submitted a modal.
    # both carry a custom_id instead of a command name, so they route the same way
    if body["type"] in (3, 5):
        # split ONCE -- everything after the first colon belongs to the handler, which is
        # what lets a custom_id carry state like "server:form:vanilla:us-east-1"
        command, subcommand = body["data"]["custom_id"].split(':', 1)

        if command == "region":
            return region.handle(subcommand, [], body)

        if command == "server":
            return server.handle(subcommand, [], body)



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

