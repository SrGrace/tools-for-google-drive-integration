
from pathlib import Path
import sys

test_dir = Path(__file__).parent
BASE_DIR = 'agent_ready_tools'
MAX_DEPTH = 10

while test_dir.name != BASE_DIR:
    test_dir = test_dir.parent
    MAX_DEPTH -= 1
    if MAX_DEPTH == 0:
        raise RecursionError(f"'{BASE_DIR}' not found in path: {__file__}")
parent_path = test_dir.parent.resolve()

sys.path.append(str(parent_path))
    
from http import HTTPStatus
import json
import mimetypes
from typing import Any, Dict, Optional
import uuid

from ibm_watsonx_orchestrate.agent_builder.tools import tool
from pydantic.dataclasses import dataclass
from requests.exceptions import HTTPError, RequestException

from agent_ready_tools.clients.google_client import get_google_client
from agent_ready_tools.utils.tool_credentials import GOOGLE_CONNECTIONS


@dataclass
class UploadFileResponse:
    """Represents the result of uploading a file in Google Drive."""

    http_code: int
    id: Optional[str] = None
    name: Optional[str] = None
    error_message: Optional[str] = None


@tool(expected_credentials=GOOGLE_CONNECTIONS)
def upload_file_google_drive(
    file_bytes: bytes,
    file_name: str,
    parent_folder_id: Optional[str] = None,
) -> UploadFileResponse:
    """
    Uploads a file to Google Drive.

    Args:
        file_bytes: The bytes of the file to be uploaded.
        file_name: The name of the file to be uploaded to Google Drive.
        parent_folder_id: Optional. The folder_id of the parent folder in Google Drive, returned by the `get_folders` tool.

    Returns:
        The result of uploading the file to Google Drive
    """

    if not isinstance(file_bytes, bytes) or not file_bytes:
        return UploadFileResponse(
            http_code=HTTPStatus.BAD_REQUEST.value,
            error_message="No file content provided or file is empty. Please provide a valid file.",
        )

    if "." not in file_name or file_name.rsplit(".", 1)[-1].strip() == "":
        return UploadFileResponse(
            http_code=HTTPStatus.BAD_REQUEST.value,
            error_message="File must include a valid extension (e.g., pdf, txt, jpg, docx). Please include a valid extension in the file name",
        )

    # Attempt to guess the MIME type of the given file name
    mime_type, _ = mimetypes.guess_type(file_name)

    # If the MIME type couldn't be determined (e.g., unknown extension or no extension),
    # default to 'application/octet-stream', which represents generic binary data
    if not mime_type:
        mime_type = "application/octet-stream"

    metadata: Dict[str, Any] = {"name": file_name}
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]

    # Using a random boundary is safer than a hardcoded one.
    boundary = boundary = f"----_Part_{uuid.uuid4().hex}"

    # Manually constructing the multipart body as per Google Drive API spec for multipart upload.
    # https://developers.google.com/drive/api/guides/manage-uploads#multipart
    parts = [
        f"--{boundary}",
        "Content-Type: application/json; charset=UTF-8",
        "",
        json.dumps(metadata),
        f"--{boundary}",
        f"Content-Type: {mime_type}",
        "",
    ]
    # The body is composed of encoded headers, the file bytes, and the closing boundary.
    multipart_body = (
        "\r\n".join(parts).encode("utf-8")
        + b"\r\n"  # Ensures separation before file bytes
        + file_bytes
        + f"\r\n--{boundary}--".encode("utf-8")
    )

    client = get_google_client()

    # The google_client seems to have stateful headers. We need to temporarily
    # set the Content-Type for this request and restore it afterwards to avoid
    # side effects on other calls using the same client instance.
    client.headers["Content-Type"] = f"multipart/related; boundary={boundary}"

    try:
        response = client.post_request(
            entity="files",
            # The service endpoint for multipart uploads is different.
            service="upload/drive",
            params={"uploadType": "multipart"},
            payload=multipart_body,
        )

        return UploadFileResponse(
            http_code=response.get("http_code", HTTPStatus.OK.value),
            id=response.get("id"),
            name=response.get("name"),
        )

    except HTTPError as e:
        # Handle cases where the API returns a non-2xx status code.
        error_message = f"Upload failed with HTTP status {e.response.status_code}."
        try:
            error_details = e.response.json().get("error", {})
            error_message += f" Message: {error_details.get('message', e.response.text)}"
        except json.JSONDecodeError:
            error_message += f" Response: {e.response.text}"
        return UploadFileResponse(http_code=e.response.status_code, error_message=error_message)
    except RequestException as e:
        # Handle network-related errors (e.g., connection timeout).
        return UploadFileResponse(
            http_code=response.get("http_code", HTTPStatus.OK.value),
            error_message=f"Upload failed due to a network error: {e}",
        )
    except Exception as e:  # pylint: disable=broad-except
        # Catch any other unexpected exceptions.
        return UploadFileResponse(
            http_code=response.get("http_code", HTTPStatus.OK.value),
            error_message=f"An unexpected error occurred during upload: {e}",
        )
