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


# =======================================MODAL==========================================
# type 9 = modal (the pop-up form). `fields` is a ready-made list the CALLER builds:
#   {"custom_id": ..., "label": ..., "placeholder": ..., "value": ..., "required": bool}
#
# two discord rules, both silent failures if you break them: a modal must be an IMMEDIATE
# response (no deferring first), and it's FIVE fields max, one per action row
def modal(custom_id, title, fields):
    return _respond({
        "type": 9,
        "data": {
            "custom_id": custom_id,
            "title": title,
            "components": [
                {
                    "type": 1,  # every text input needs its own action row wrapper
                    "components": [
                        {
                            "type": 4,   # type 4 = text input
                            "style": 1,  # style 1 = single line (2 would be a paragraph box)
                            "custom_id": field["custom_id"],
                            "label": field["label"],
                            "placeholder": field.get("placeholder", ""),
                            "value": field.get("value", ""),
                            "required": field.get("required", True),
                        }
                    ],
                }
                for field in fields
            ],
        },
    })


# ====================================AUTOCOMPLETE======================================
# type 8 = the suggestion list shown while someone's still typing an option. `choices` is
# a list of {"name": shown, "value": sent}. 25 MAX -- more and discord rejects the lot
def autocomplete(choices):
    return _respond({
        "type": 8,
        "data": {"choices": choices},
    })


# ==================================READ MODAL FIELDS===================================
# flatten a modal submit to {custom_id: value}. values sit one layer deeper than
# component interactions -- each input is wrapped in its own action row
def modal_values(body):
    return {
        row["components"][0]["custom_id"]: row["components"][0]["value"]
        for row in body["data"]["components"]
    }
