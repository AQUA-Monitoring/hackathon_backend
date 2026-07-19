import os
import requests
from requests.exceptions import RequestException


def get_api_config() -> tuple[str, str, str]:
    url = os.getenv("API_URL", "").rstrip("/")
    email = os.getenv("API_EMAIL", "")
    password = os.getenv("API_PASSWORD", "")
    if not url or not email or not password:
        raise ValueError(
            "API_URL, API_EMAIL e API_PASSWORD devem estar definidas no .env"
        )
    return url, email, password


def login() -> str:
    url, email, password = get_api_config()
    resp = requests.post(
        f"{url}/api/sync/token/",
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code in {401, 403}:
        raise RuntimeError("Falha na autenticação remota: credenciais inválidas")
    if resp.status_code != 200:
        raise RuntimeError(f"Falha na autenticação remota (HTTP {resp.status_code})")
    return resp.json()["access"]
