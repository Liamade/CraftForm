# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  OPERATIONS LAMBDA  ::  responses.py                                         ║
# ║  Shared builders for the discord interaction responses we send back through   ║
# ║  api gateway. dumb + domain-agnostic -- they know discord's shapes, not ours. ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# ==========================================================================================
#                            DISCORD INTERACTION RESPONSES
# ==========================================================================================
# every command ends by handing discord a json packet wrapped in the api gateway envelope.
# these helpers build those packets so the command files don't repeat the boilerplate :)
# ------------------------------------------------------------------------------------------
import json

# discord flag that marks a reply as ephemeral -- only the user who ran the command sees it
EPHEMERAL = 64


# =================================API GATEWAY ENVELOPE==================================
# private -- wrap a discord interaction payload in the api gateway response shape.
# everything below funnels through here so the envelope lives in exactly one place
def _respond(payload):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


# =======================================PONG===========================================
# type 1 = pong -- discord's setup ping just wants a hello back :)
def pong():
    return _respond({"type": 1})


# =====================================DEFERRED=========================================
# type 5 = deferred -- shows the "thinking..." spinner; something follows up later
def deferred():
    return _respond({"type": 5})



# ===================================PLAIN MESSAGE======================================
# type 4 = immediate ephemeral text reply -- used when there's nothing fancy to show
def plain_message(text):
    return _respond({
        "type": 4,
        "data": {
            "content": text,
            "flags": EPHEMERAL,
        },
    })


# =====================================DROP DOWN========================================
# type 4 with a string select menu. `options` is a ready-made list of
# {"label": ..., "value": ...} dicts -- the CALLER builds those so we stay domain-agnostic
def drop_down(content, custom_id, placeholder, options):
    return _respond({
        "type": 4,
        "data": {
            "content": content,
            "flags": EPHEMERAL,
            "components": [
                {
                    "type": 1,  # type 1 = action row (container for components)
                    "components": [
                        {
                            "type": 3,  # type 3 = string select menu
                            "custom_id": custom_id,
                            "placeholder": placeholder,
                            "options": options,
                        }
                    ],
                }
            ],
        },
    })
