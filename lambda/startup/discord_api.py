# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  STARTUP LAMBDA  ::  discord_api.py                                          ║
# ║  Handles all Discord API interactions during initial deployment.             ║
# ║  Registers slash commands and sets the interactions endpoint.                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


# ==========================================================================================
#                            IMPORTS AND DEPENDENCIES
# ==========================================================================================
import urllib3
import json
from pathlib import Path


# ==========================================================================================
#                                    DISCORD CLASS
# ==========================================================================================
class DiscordClient:

    def __init__(self, bot_token, app_id):
        # discord bot token
        self.bot_token = bot_token
        # discord app id
        self.app_id = app_id

        # open an http client
        self.http = urllib3.PoolManager()

        # headers for the http request
        self.headers = {
            "Authorization": f"Bot {self.bot_token}",  # authenticate the request with the bot token
            "Content-Type": "application/json",  # specify that the request body is in JSON
        }

    # private method to handle all http requests
    def _request(self, method, path, body):
        return self.http.request(
            method,
            f"https://discord.com/api/v10/applications/{self.app_id}{path}",
            headers={**self.headers, "Content-Type": "application/json"},
            body=json.dumps(body) if body is not None else None,
        )
    
    def send_api_url(self, api_url):

        # send a post to discord API to set the interactions endpoint to the API Gateway URL
        response = self._request(
            "PATCH",
            body = {
                "interactions_endpoint_url": api_url  # the API Gateway URL to set as the interactions endpoint
            }
        )

        # make sure the request was successful
        if response.status != 200:
            raise RuntimeError(f"Failed to set Discord interactions endpoint: {response.status} - {response.data} :(")
        
        else:
            print("API Gateaway URL set on Discord application :)")

    def register_commands(self):

        # register the slash commands with the Discord API
        response = self._request(
            "PUT",
            "/commands",
            body = json.loads((Path(__file__).parent / "slash_commands.json").read_text())  # the slash commands from "slash_commands.json"
        )

        if response.status != 200:
            raise RuntimeError(f"Failed to register slash commands: {response.status} - {response.data} :(")
        else:
            print("Slash commands registered with Discord :)")

