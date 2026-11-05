import pandas as pd
import numpy as np

inp = r"C:\Users\smorozov\Desktop\НИРС\requests_merged_labeled.csv"
out = r"C:\Users\smorozov\Desktop\НИРС\windows_features.csv"

WINDOW = 30
STEP = 5

df = pd.read_csv(inp)
df["requestTime"] = pd.to_datetime(df["requestTime"], utc=True, errors="coerce")
for c in ["x", "y", "z"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

df = df.dropna(subset=["requestTime", "x", "y", "z", "sourceLabel"]).sort_values("requestTime").copy()

# группировка: если sessionId есть — по userIp+sessionId, иначе по userIp
sid = df["sessionId"].fillna("").astype(str).str.strip()
df["groupId"] = np.where(sid != "", df["userIp"].astype(str) + "|" + sid, df["userIp"].astype(str) + "|no-session")

rows = []
for gid, g in df.groupby("groupId"):
    g = g.sort_values("requestTime").reset_index(drop=True)
    if len(g) < WINDOW:
        continue

    for i in range(0, len(g) - WINDOW + 1, STEP):
        w = g.iloc[i:i+WINDOW]

        x = w["x"].to_numpy()
        y = w["y"].to_numpy()
        z = w["z"].to_numpy()
        t = w["requestTime"].astype("int64").to_numpy() / 1e9

        dx = np.diff(x)
        dy = np.diff(y)
        dt = np.diff(t)
        dt = np.where(dt <= 0, 1e-6, dt)

        rows.append({
            "groupId": gid,
            "startTime": w["requestTime"].iloc[0],
            "endTime": w["requestTime"].iloc[-1],
            "sourceLabel": w["sourceLabel"].mode().iloc[0],

            "req_count": len(w),
            "x_std": float(np.std(x)),
            "y_std": float(np.std(y)),
            "z_std": float(np.std(z)),
            "x_unique": int(len(np.unique(x))),
            "y_unique": int(len(np.unique(y))),
            "z_unique": int(len(np.unique(z))),
            "mean_abs_dx": float(np.mean(np.abs(dx))) if len(dx) else 0.0,
            "mean_abs_dy": float(np.mean(np.abs(dy))) if len(dy) else 0.0,
            "mean_dt": float(np.mean(dt)) if len(dt) else 0.0,
            "std_dt": float(np.std(dt)) if len(dt) else 0.0,
            "min_dt": float(np.min(dt)) if len(dt) else 0.0,
            "max_dt": float(np.max(dt)) if len(dt) else 0.0,
        })

wf = pd.DataFrame(rows)
wf.to_csv(out, index=False)

print("saved:", out)
print("windows:", len(wf))
print(wf["sourceLabel"].value_counts().to_string())