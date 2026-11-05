import argparse
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import urllib3
import pandas as pd
from dotenv import load_dotenv

# Нам потребуется функция, с помощью которой описываем интерфейс командной строки
# 1) Создаём ArgumentParser
# 2) регистрируем аргументы 
# 3) возвращаем Namespace с полями gte, local, tz, index, node, user, password, size, json_out, csv_out.

DEFAULT_INDEX = "requests"
DEFAULT_NODE = "https://localhost:9200"
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--gte",)
    g.add_argument("--local",)
    p.add_argument(
        "--tz",
        default="Europe/Moscow",
        help='Имя IANA-зоны для --local (по умолчанию Europe/Moscow)',
    )
    p.add_argument("--index", default=os.environ.get("OPENSEARCH_INDEX", DEFAULT_INDEX))
    p.add_argument("--node", default=os.environ.get("OPENSEARCH_NODE", DEFAULT_NODE))
    p.add_argument("--user", default=os.environ.get("OPENSEARCH_USER", "admin"))
    p.add_argument("--password",default=os.environ.get("OPENSEARCH_PASSWORD", ""),)
    p.add_argument("--size", type=int, default=10_000, help="Максимум хитов за запрос")
    p.add_argument(
        "--json-out",
        default="tmp_files/requests_raw.json",
        help="Сырые хиты OpenSearch (JSON)",
    )
    p.add_argument(
        "--csv-out",
        default="tmp_files/requests_raw.csv",
        help="Плоская таблица для pandas / ML",
    )
    return p.parse_args()
#Также потребуется функция чтобы привести время в единый вид
def gte_iso_from_args(ns: argparse.Namespace) -> str:
    if ns.gte:
        return ns.gte
    dt = datetime.strptime(ns.local.strip(), "%d.%m.%Y %H:%M")
    dt = dt.replace(tzinfo=ZoneInfo(ns.tz))
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
#Делаем запрос на получение логов
def fetch_scroll(
    node: str,
    index: str,
    auth: tuple[str, str],
    gte_iso: str,
    size: int,
) -> list[dict]:
    url = f"{node.rstrip('/')}/{index}/_search"
    q = {
        "query": {"range": {"requestTime": {"gte": gte_iso}}},
        "size": size,
        "sort": [{"requestTime": {"order": "asc"}}],
    }
    r = requests.post(
        url,
        auth=auth,
        json=q,
        headers={"Content-Type": "application/json"},
        verify=False,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("hits", {}).get("hits", [])


#Преобразовываем в csv для удобного чтения
def hits_to_csv(hits: list[dict]) -> pd.DataFrame:
    rows = []
    for hit in hits:
        s = hit.get("_source", {})
        p = s.get("parameters", {}) or {}
        rows.append(
            {
                "requestTime": s.get("requestTime"),
                "userIp": s.get("userIp"),
                "x": p.get("x"),
                "y": p.get("y"),
                "z": p.get("z"),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["requestTime"] = pd.to_datetime(df["requestTime"], errors="coerce", utc=True)
    for c in ["x", "y", "z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["requestTime", "x", "y", "z"]).sort_values("requestTime")



def main() -> None:
    ns = parse_args()


    gte_iso = gte_iso_from_args(ns)
    auth = (ns.user, ns.password)

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    hits = fetch_scroll(ns.node, ns.index, auth, gte_iso, ns.size)

    with open(ns.json_out, "w", encoding="utf-8") as f:
        json.dump({"hits": {"hits": hits}}, f, ensure_ascii=False, indent=2)

    df = hits_to_csv(hits)
    df.to_csv(ns.csv_out, index=False)

    print(f"Дата от: {gte_iso}")
    print(f"вхождений: {len(hits)}")
    print(f"строк всего: {len(df)}")
    print(f"сохранено: {ns.json_out}, {ns.csv_out}")



load_dotenv() 
sys.argv = [
    "export.py",
    "--local", "01.09.2024 00:00",  
    "--size", "10000",
]
main() # проверим что он собирает логи как и в былые времена