import os
from pathlib import Path

from ibm_watsonx_orchestrate.cli.config import DEFAULT_CONFIG_FILE, DEFAULT_CONFIG_FILE_FOLDER
from ibm_watsonx_orchestrate.client.utils import is_local_dev


def in_adk_env() -> bool:
    """
    Determines whether this code is running in a local ADK environment.

    Returns:
        Whether the env is a local ADK env.
    """
    # can get permission errors when orchestrate tries to read cfg file to determine if local
    config_path = Path(DEFAULT_CONFIG_FILE_FOLDER) / DEFAULT_CONFIG_FILE
    try:
        if config_path.exists() and os.access(str(config_path), os.R_OK):
            if is_local_dev():
                return True
    except PermissionError:  # Local envs should be able to access the config
        pass
    return False


def in_pants_env() -> bool:
    """
    Determines whether this code is running in a pants env (executed via `pants run ...`, `pants
    test ...` or `pants repl ...`). `pants run ...` and `pants repl ...` invocations don't seem to
    use a tmp sandbox dir, but do have pants-related env vars.

    Returns:
        Whether the env is a pants env.
    """
    return "PANTS_VERSION" in os.environ or "pants-sandbox" in os.getcwd()
