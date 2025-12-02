import json
import os
from pathlib import Path
from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth


class AuthManager:
    """Base Authentication Manager."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        initial_bearer_token: str,
        initial_refresh_token: str,
        token_cache_file: str,
    ):
        """
        Args:
            token_url: The URL for authentication tokens.
            client_id: The client_id to use for authentication.
            client_secret: The client_secret to use for authentication.
            initial_bearer_token: The initial bearer token.
            initial_refresh_token: The initial refresh token.
            token_cache_file: The name of the credentials cache file in the tools runtime env. This will now be primarily
                              for compatibility; actual caching will be in-memory due to permissions.
        """
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        # self.initial_bearer_token = initial_bearer_token
        # self.initial_refresh_token = initial_refresh_token
        self.auth = HTTPBasicAuth(client_id, client_secret)
        self.headers = {"Content-Type": "application/x-www-form-urlencoded"}
        self.bearer_token_resp_key = "access_token"
        self.refresh_token_resp_key = "refresh_token"
        self.request_data_template = "grant_type=refresh_token&refresh_token={0}"
        # self.creds_path = Path("/shared-data/" + token_cache_file)
        self.pants_sandbox_substr = "pants-sandbox"

        # --- NEW: In-memory token storage ---
        self._in_memory_bearer_token: Optional[str] = initial_bearer_token
        self._in_memory_refresh_token: Optional[str] = initial_refresh_token
        # --- END NEW ---

        # The creds_path will still be set, but its file operations will be guarded
        self.creds_path = Path("/shared-data/" + token_cache_file)
        self._can_write_to_cache = False # Flag to track if we can write to disk
        try:
            # Attempt to check if the directory is writable
            if self.creds_path.parent.is_dir() and os.access(self.creds_path.parent, os.W_OK):
                self._can_write_to_cache = True
            else:
                print(f"WARNING: Cache directory {self.creds_path.parent} is not writable. Tokens will be stored in-memory only and will not persist across executions.")
        except OSError as e:
            print(f"WARNING: Error checking cache directory writability ({e}). Tokens will be stored in-memory only.")


    def _get_cred_from_server_cache(self, key: str) -> Optional[str]:
        """Gets a given key's value from the cached server side."""
        # if not self.creds_path.is_file():
        #     return None
        # with open(self.creds_path) as f:
        #     d: Dict[str, str] = json.load(f)
        #     return d.get(key)

        # --- MODIFIED: Prioritize in-memory, then try disk if writable ---
        if key == self.bearer_token_resp_key:
            return self._in_memory_bearer_token
        elif key == self.refresh_token_resp_key:
            return self._in_memory_refresh_token
        # If we can write to cache, also try to load from disk as it might have persisted from a previous run
        if self._can_write_to_cache and self.creds_path.is_file():
            try:
                with open(self.creds_path) as f:
                    d: Dict[str, str] = json.load(f)
                    return d.get(key)
            except Exception as e:
                print(f"WARNING: Error reading from disk cache ({e}). Falling back to in-memory/initial tokens.")
        return None
        # --- END MODIFIED ---

    def _update_server_creds_cache(self, creds: Dict[str, str]) -> None:
        """Updates the credentials cache."""
        # with open(self.creds_path, "w") as f:
        #     json.dump(creds, f)

        # --- MODIFIED: Update in-memory, then try disk if writable ---
        if self.bearer_token_resp_key in creds:
            self._in_memory_bearer_token = creds[self.bearer_token_resp_key]
        if self.refresh_token_resp_key in creds:
            self._in_memory_refresh_token = creds[self.refresh_token_resp_key]

        if self._can_write_to_cache:
            try:
                # Ensure the directory exists before writing the file
                self.creds_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.creds_path, "w") as f:
                    json.dump(creds, f)
            except Exception as e:
                print(f"WARNING: Failed to write to disk cache ({e}). Tokens only stored in-memory.")
        # --- END MODIFIED ---

    def refresh_bearer_token(self) -> None:
        """Gets and caches a bearer_token using a refresh_token from the auth URL using the loaded
        credentials."""

        if self.pants_sandbox_substr in os.getcwd():
            return
        refresh_token = (
            self._get_cred_from_server_cache(self.refresh_token_resp_key)
            or self.initial_refresh_token
        )

        request_data = self.request_data_template.format(refresh_token)
        response = requests.post(
            url=self.token_url, auth=self.auth, headers=self.headers, data=request_data
        )

        response.raise_for_status()
        resp: Dict[str, Optional[str]] = response.json()
        tokens = {
            key: str(resp[key])
            for key in (self.bearer_token_resp_key, self.refresh_token_resp_key)
            if resp.get(key) is not None
        }
        self._update_server_creds_cache(tokens)

    def get_bearer_token(self) -> str:
        """Fetches bearer token."""
        # from_srv = self._get_cred_from_server_cache(self.bearer_token_resp_key)
        # return from_srv or self.initial_bearer_token

        # --- MODIFIED: Prioritize in-memory, then try disk if writable ---
        if self._in_memory_bearer_token:
            return self._in_memory_bearer_token
        
        # Fallback to disk if possible (though _get_cred_from_server_cache handles this)
        from_srv = self._get_cred_from_server_cache(self.bearer_token_resp_key)
        if from_srv:
            return from_srv
        # --- END MODIFIED ---
        return self.initial_bearer_token


class GoogleAuthManager(AuthManager):
    """An Authentication Manager for Google."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        initial_bearer_token: str,
        initial_refresh_token: str,
    ):
        """
        Args:
            token_url: The URL for authentication tokens.
            client_id: The client_id to use for authentication.
            client_secret: The client_secret to use for authentication.
            initial_bearer_token: The initial bearer token.
            initial_refresh_token: The initial refresh token.
        """
        token_cache_file = "google_auth.json"
        super().__init__(
            token_url,
            client_id,
            client_secret,
            initial_bearer_token,
            initial_refresh_token,
            token_cache_file,
        )

    def refresh_bearer_token(self) -> None:
        """Gets and caches a bearer_token using a refresh_token from the auth URL using the loaded
        credentials."""
        if self.pants_sandbox_substr in os.getcwd():
            return
        refresh_token = (
            self._get_cred_from_server_cache(self.refresh_token_resp_key)
            or self.initial_refresh_token
        )
        # payload = {
        #     "grant_type": "refresh_token",
        #     "refresh_token": refresh_token,
        # }
        # response = requests.post(
        #     url=self.token_url, auth=self.auth, headers=self.headers, data=payload
        # )
        # response.raise_for_status()
        # resp: Dict[str, Optional[str]] = response.json()
        # tokens = {
        #     self.bearer_token_resp_key: str(resp[self.bearer_token_resp_key]),
        #     self.refresh_token_resp_key: refresh_token,
        # }
        # self._update_server_creds_cache(tokens)

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,  # Add client_id to payload for Google
            "client_secret": self.client_secret, # Add client_secret to payload for Google
        }
        # For Google, the client_id and client_secret should be in the payload,
        # and typically, Basic Auth is not used here if they are in the body.
        # We'll remove 'auth=self.auth' from the post request for Google.
        response = requests.post(
            url=self.token_url,
            headers=self.headers, # self.headers already includes "Content-Type": "application/x-www-form-urlencoded"
            data=payload # Use payload directly, requests will handle encoding
        )
        response.raise_for_status()
        resp: Dict[str, Optional[str]] = response.json()

        # Google's refresh token can sometimes remain the same, so we explicitly take the new access_token
        # and either the new refresh_token if provided, or the old one if not.
        new_access_token = str(resp[self.bearer_token_resp_key])
        new_refresh_token = resp.get(self.refresh_token_resp_key, refresh_token) # Keep old refresh token if new one isn't provided

        tokens = {
            self.bearer_token_resp_key: new_access_token,
            self.refresh_token_resp_key: new_refresh_token,
        }
        self._update_server_creds_cache(tokens)


class HubSpotAuthManager(AuthManager):
    """An Authentication Manager for HubSpot."""

    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        initial_bearer_token: str,
        initial_refresh_token: str,
    ):
        """
        Args:
            token_url: The URL for authentication tokens.
            client_id: The client_id to use for authentication.
            client_secret: The client_secret to use for authentication.
            initial_bearer_token: The initial bearer token.
            initial_refresh_token: The initial refresh token.
        """
        token_cache_file = "hubspot_auth.json"
        super().__init__(
            token_url,
            client_id,
            client_secret,
            initial_bearer_token,
            initial_refresh_token,
            token_cache_file,
        )

    def refresh_bearer_token(self) -> None:
        """Gets and caches a bearer_token using a refresh_token from the auth URL using the loaded
        credentials."""
        if self.pants_sandbox_substr in os.getcwd():
            return
        refresh_token = (
            self._get_cred_from_server_cache(self.refresh_token_resp_key)
            or self.initial_refresh_token
        )
        # client_id = self._get_cred_from_server_cache(self.client_id) or self.client_id
        # client_secret = self._get_cred_from_server_cache(self.client_secret) or self.client_secret
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(url=self.token_url, headers=self.headers, data=payload)
        response.raise_for_status()
        resp: Dict[str, Optional[str]] = response.json()
        tokens = {
            self.refresh_token_resp_key: refresh_token,
            self.bearer_token_resp_key: str(resp[self.bearer_token_resp_key]),
        }
        self._update_server_creds_cache(tokens)
