import json
import pandas as pd

files = [
    (r"C:\Users\smorozov\Desktop\НИРС\requests_raw.json", "clean"),
    (r"C:\Users\smorozov\Desktop\НИРС\requests_raw2.json", "synthetic"),
]

out = r"C:\Users\smorozov\Desktop\НИРС\requests_merged_labeled.csv"

rows = []
for path, label in files:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for hit in data["hits"]["hits"]:
        s = hit.get("_source", {})
        p = s.get("parameters", {}) or {}
        session_id = p.get("sessionId", "")

        rows.append({
            "requestTime": s.get("requestTime"),
            "userIp": s.get("userIp"),
            "sessionId": session_id,      # оставляем для дебага/группировки
            "hasSessionId": int(bool(session_id)),
            "x": p.get("x"),
            "y": p.get("y"),
            "z": p.get("z"),
            "sourceLabel": label,         # только для оценки, НЕ фича
        })

df = pd.DataFrame(rows)
df["requestTime"] = pd.to_datetime(df["requestTime"], errors="coerce", utc=True)
for c in ["x", "y", "z"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df = df.dropna(subset=["requestTime", "x", "y", "z"]).sort_values("requestTime")
df.to_csv(out, index=False)

print("saved:", out)
print("rows:", len(df))
print(df["sourceLabel"].value_counts().to_string())
print("hasSessionId by label:")
print(df.groupby("sourceLabel")["hasSessionId"].mean().to_string())