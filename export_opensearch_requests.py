"""
Выгрузка индекса OpenSearch `requests` (логи Rule-Based Filter) в CSV / Parquet.

Зависимости:
  pip install requests
  # опционально для Parquet:
  pip install pandas pyarrow

Перед запуском задайте пароль OpenSearch (тот же, что OPENSEARCH_INITIAL_ADMIN_PASSWORD):
  PowerShell:
    $env:OPENSEARCH_PASSWORD="Admin123!Strong"
    python export_opensearch_requests.py

При самоподписанном HTTPS на localhost VERIFY_SSL=0 (по умолчанию).
"""
from __future__ import annotations

import csv
import json
import os
import sys
from typing import Any, Generator, Iterator

import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "https://localhost:9200")
OPENSEARCH_USER = os.environ.get("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.environ.get("OPENSEARCH_PASSWORD", "Admin123!Strong")
INDEX_NAME = os.environ.get("OPENSEARCH_INDEX", "requests")
VERIFY_SSL = os.environ.get("VERIFY_SSL", "0").lower() in ("1", "true", "yes")
SCROLL_SIZE = int(os.environ.get("SCROLL_SIZE", "500"))
SCROLL_KEEPALIVE = os.environ.get("SCROLL_KEEPALIVE", "2m")
OUTPUT_CSV = os.environ.get("OUTPUT_CSV", "requests_export.csv")
OUTPUT_PARQUET = os.environ.get("OUTPUT_PARQUET", "requests_export.parquet")


def _auth() -> tuple[str, str] | None:
    if not OPENSEARCH_PASSWORD:
        return None
    return OPENSEARCH_USER, OPENSEARCH_PASSWORD


def scroll_documents() -> Generator[dict[str, Any], None, None]:
    """Итерирует по всем документам индекса через Search Scroll API."""
    base = OPENSEARCH_URL.rstrip("/")
    search_url = f"{base}/{INDEX_NAME}/_search?scroll={SCROLL_KEEPALIVE}"
    body: dict[str, Any] = {
        "size": SCROLL_SIZE,
        "query": {"match_all": {}},
    }
    r = requests.post(
        search_url,
        json=body,
        auth=_auth(),
        verify=VERIFY_SSL,
        timeout=120,
    )
    if r.status_code == 401:
        print(
            "401 Unauthorized",
            file=sys.stderr,
        )
        sys.exit(1)
    if r.status_code == 404:
        print(
            f"40",
            file=sys.stderr,
        )
        sys.exit(1)
    r.raise_for_status()
    data = r.json()
    scroll_id = data["_scroll_id"]
    try:
        while True:
            for hit in data.get("hits", {}).get("hits", []):
                src = hit.get("_source")
                if src is not None:
                    yield src
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            r = requests.post(
                f"{base}/_search/scroll",
                json={"scroll": SCROLL_KEEPALIVE, "scroll_id": scroll_id},
                auth=_auth(),
                verify=VERIFY_SSL,
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            scroll_id = data["_scroll_id"]
    finally:
        try:
            requests.delete(
                f"{base}/_search/scroll",
                json={"scroll_id": scroll_id},
                auth=_auth(),
                verify=VERIFY_SSL,
                timeout=30,
            )
        except requests.RequestException:
            pass


def flatten_row(doc: dict[str, Any]) -> dict[str, Any]:
    params = doc.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}
    return {
        "userIp": doc.get("userIp", ""),
        "requestTime": doc.get("requestTime", ""),
        "z": params.get("z", ""),
        "x": params.get("x", ""),
        "y": params.get("y", ""),
        "sessionId": params.get("sessionId", ""),
        "parameters_json": json.dumps(params, ensure_ascii=False),
    }


def iter_rows() -> Iterator[dict[str, Any]]:
    for doc in scroll_documents():
        yield flatten_row(doc)


def main() -> None:
    if not OPENSEARCH_PASSWORD:
        print(
            "Не задан OPENSEARCH_PASSWORD.\n"
        
            file=sys.stderr,
        )
        sys.exit(1)

    rows = list(iter_rows())
    if not rows:
        print(f"Индекс «{INDEX_NAME}» пуст или не существует.", file=sys.stderr)
        sys.exit(0)

    fieldnames = list(rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"CSV: {len(rows)} строк  {OUTPUT_CSV}")

    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(OUTPUT_PARQUET, index=False)
        print(f"Parquet: {len(rows)} строк  {OUTPUT_PARQUET}")
    except ImportError:
        print("Parquet пропущен")


if __name__ == "__main__":
    main()
