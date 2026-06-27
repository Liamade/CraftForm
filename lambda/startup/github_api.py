# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                               CraftForm                                      ║
# ╠══════════════════════════════════════════════════════════════════════════════╣
# ║  STARTUP LAMBDA  ::  github_api.py                                           ║
# ║  Handles all GitHub API interactions during initial deployment.              ║
# ║  Forks repo, enables Actions, and pushes AWS secrets.                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


# ==========================================================================================
#                            IMPORTS AND DEPENDENCIES
# ==========================================================================================
import time
import json
import urllib3
from nacl import encoding, public
from base64 import b64encode

# ==========================================================================================
#                                      GITHUB CLASS
# ==========================================================================================

class GithubClient:
    # base github url - shared between every instance in the class
    BASE = "https://api.github.com"

    # function to define itself on startup
    def __init__(self, pat, username):
        
        # github pat
        self.pat = pat
        # github username
        self.username = username

        # open an http client
        self.http = urllib3.PoolManager()

        # base headers for all interactions
        self.headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json",
        }

    # a private method to do all the http request
    def _request(self, method, path, body=None):
        return self.http.request(
            method,
            f"{self.BASE}{path}",
            headers={**self.headers, "Content-Type": "application/json"},
            body=json.dumps(body) if body is not None else None,
        )

    # ==================================== FORK REPO ====================================
    # private function to wait for status on forked repo
    def _wait_for_fork(self, attempts=10):

        for _ in range(attempts):
            if self._request("GET", f"/repos/{self.username}/CraftForm").status == 200:
                print("Fork is ready :)")
                return
            time.sleep(3)
        raise TimeoutError("Fork took too long :(")
    
    # actual public callable function
    def fork_repo(self):

        # make sure the repo isn't already forked
        if self._request("GET", f"/repos/{self.username}/CraftForm").status == 200:
            print("Repo already forked :)")
            return
        
        # fork the repo if need be
        response = self._request("POST", "/repos/Liamade/CraftForm/forks")

        # check on response return status code
        if response.status != 202:
            raise RuntimeError(f"Fork failed: {response.status} - {response.data}")
        
        # call waiting function
        self._wait_for_fork()
    
    # ================================== ENABLE ACTIONS ==================================
    def enable_actions(self):
        # create the body of the request
        body = {
            "enabled": True,  # enable GitHub Actions in the forked repo
            "allowed_actions": "all",  # allow all actions in GitHub Actions
        }
        # make the http request to enable actions
        response = self._request(
            "PUT",
            f"/repos/{self.username}/CraftForm/actions/permissions",
            body
        )

        # make sure the request was succesful
        if response.status != 204:  # GitHub API returns a 204 No Content status code for a successful request to enable Actions
            raise RuntimeError(f"Failed to enable GitHub Actions: {response.status} - {response.data} :(")
        else:
            print("GitHub Actions enabled :)")

    # =================================== PUSH SECRETS ===================================
    # print method to encrypt secrets and be called on by "push_secrets"
    @staticmethod   # this function doesn't need the "self" instance
    def _encrypt_secret(public_key, secret):
        # decode the Bse64-encoded key GitHub returns
        key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())

        # create a sealed box with that public key
        sealed_box = public.SealedBox(key)

        # encrypt the secret with the sealed box and key, then Base64-encode the result so it can be sent as a string in the GitHub API request
        encrypted = sealed_box.encrypt(secret.encode("utf-8"))

        # encode the result as base64 so it can be sent as a string
        return b64encode(encrypted).decode("utf-8")

    def push_secrets(self, secret_dict):

        # capture the public key from Github to encrypt the secret before pushing it
        key_response = self._request(
            "GET",
            f"/repos/{self.username}/CraftForm/actions/secrets/public-key",
        )

        # make sure the public key request was successful
        if key_response.status != 200:
            raise RuntimeError(f"Failed to get public key: {key_response.status} - {key_response.data} :(")
        else:
            print("Public key cam back :)")

        # extract the public key from the response
        # we capture both the public key and the key ID
        # Public Key - used to encrypt the secret before sending it to GitHub
        # Key ID     - included in the request to GitHub when pushing the secret
        key_data = json.loads(key_response.data.decode("utf-8"))
        public_key = key_data["key"]  # the public key to encrypt secrets with
        key_id = key_data["key_id"]  # the key ID to include in the request to GitHub when pushing secret

        # repeat for every entry in the dictionary
        for secret_name, secret in secret_dict.items():

            # encrypt the GitHub secret  with the public key
            # GitHub requires that all secrets pushed to GitHub are encrypted with the Public Key captured
            encrypted_secret = self._encrypt_secret(public_key, secret)

            # push the encrypted secret to GitHub using the API - this will make the secret available in the forked repo
            # GitHub Actions will be able to access this secret and use it within it's workflows and pipelines
            secret_response = self._request(
                "PUT",
                f"/repos/{self.username}/CraftForm/actions/secrets/{secret_name}",  # secret name comes from the dict key
                body = {
                    "encrypted_value": encrypted_secret,
                    "key_id": key_id
                }
            )

            # make sure the request to push the secret was successful
            if secret_response.status not in [
                201,
                204,
            ]:  # GitHub API returns a 201 for a new secret and 204 for an updated secret
                raise Exception(f"Failed to push secret: {secret_response.status} - {secret_response.data} :(")
            else:
                print(f"Secret {secret_name} placed :)")





    # ================================== PUSH VARIABLES ==================================
    def push_variables(self, var_dict):

        # repeat this process for every entry in the dictionary
        for var_name, var in var_dict.items():
            response = self._request(
                "POST",
                f"/repos/{self.username}/CraftForm/actions/variables",
                body = {
                    "name": var_name,
                    "value": var
                }
            )

            # ALREADY EXISTS REPONSE
            if response.status == 409:
                print("Variable already exists, patching the variable instead")
                response = self._request(
                    "PATCH",
                    f"/repos/{self.username}/CraftForm/actions/variables/{var_name}",
                    body = {
                       "value": var
                    }
                )

                # FAILURE RESPONSE - PATCH
                if response.status != 204:
                    raise RuntimeError(f"Failed to update {var_name}: {response.status} - {response.data} :(")

                # SUCCESS RESPONSE
                else:
                    print(f"Successfully updated {var_name} :)")

            # SUCCESS RESPONSE - POST
            elif response.status == 201:
                print(f"Successfully placed {var_name} :)")

            # FAILURE RESPONSE - POST
            else:
                raise Exception(f"Failed to POST {var_name}: {response.status} - {response.data} :(")

