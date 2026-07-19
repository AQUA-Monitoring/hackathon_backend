import os
import time
from urllib.parse import urljoin, urlsplit

import requests
from requests.exceptions import RequestException

from core.sync.auth import get_api_config

DEFAULT_SYNC_MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_SYNC_MAX_FILE_BYTES = 1024 * 1024 * 1024


def get_sync_max_file_bytes() -> int:
    raw_value = os.getenv("SYNC_MAX_FILE_BYTES")
    if raw_value is None or not raw_value.strip():
        return DEFAULT_SYNC_MAX_FILE_BYTES
    try:
        max_bytes = int(raw_value)
    except ValueError as exc:
        raise ValueError("SYNC_MAX_FILE_BYTES deve ser um número inteiro") from exc
    if max_bytes <= 0 or max_bytes > MAX_SYNC_MAX_FILE_BYTES:
        raise ValueError(
            f"SYNC_MAX_FILE_BYTES deve estar entre 1 e {MAX_SYNC_MAX_FILE_BYTES}"
        )
    return max_bytes


def fetch_all(endpoint: str, token: str, page_size: int = 100) -> list[dict]:
    url_base, _, _ = get_api_config()
    url_base = url_base.rstrip("/")
    url = f"{url_base}{endpoint}"
    params = {"page_size": page_size}

    headers = {"Authorization": f"Bearer {token}"}
    results: list[dict] = []

    while url:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except RequestException as e:
            raise RuntimeError(f"Erro ao acessar {url}: {e}") from e

        if isinstance(data, list):
            results.extend(data)
            break

        if "results" in data:
            results.extend(data["results"])
            url = data.get("next")
            params = {}
        else:
            results.append(data)
            break

        if url:
            time.sleep(0.2)

    return results


def fetch_file(url: str, token: str, max_bytes: int | None = None) -> bytes:
    """Download a media file from the configured remote API.

    Media URLs returned by Django are normally relative.  Resolving them against
    ``API_URL`` also prevents a payload from making the sync process fetch an
    arbitrary host.
    """
    if max_bytes is None:
        max_bytes = get_sync_max_file_bytes()
    elif max_bytes <= 0 or max_bytes > MAX_SYNC_MAX_FILE_BYTES:
        raise ValueError(f"max_bytes deve estar entre 1 e {MAX_SYNC_MAX_FILE_BYTES}")

    base_url, _, _ = get_api_config()
    base_url = f"{base_url.rstrip('/')}/"
    resolved_url = urljoin(base_url, url)

    base = urlsplit(base_url)
    target = urlsplit(resolved_url)
    if target.scheme not in {"http", "https"} or target.netloc != base.netloc:
        raise ValueError("A URL do arquivo não pertence à API remota configurada")

    try:
        with requests.get(
            resolved_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            stream=True,
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise ValueError(f"Arquivo excede o limite de {max_bytes} bytes")

            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError(f"Arquivo excede o limite de {max_bytes} bytes")
            return bytes(content)
    except RequestException as exc:
        raise RuntimeError(f"Erro ao baixar arquivo de {resolved_url}: {exc}") from exc
