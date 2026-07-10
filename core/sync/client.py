import time
import requests
from requests.exceptions import RequestException

from core.sync.auth import get_api_config


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
