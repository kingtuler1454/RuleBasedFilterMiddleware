"""
Перебор IsolationForest: train только на clean, оценка на всех окнах.

Вход:  data/processed/requests_merged_labeled.csv
Выход: data/processed/experiments_iforest.csv
       data/processed/plots/*.png

Запуск из корня репозитория:
  python scripts/ml/experiments_iforest.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    raise SystemExit(
        "Нужен matplotlib: python -m pip install matplotlib\n" + str(e)
    ) from e

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"
INPUT_CSV = DATA / "requests_merged_labeled.csv"
OUT_CSV = DATA / "experiments_iforest.csv"
PLOTS = DATA / "plots"

FEATURE_COLS = [
    "req_count",
    "x_std",
    "y_std",
    "z_std",
    "x_unique",
    "y_unique",
    "z_unique",
    "mean_abs_dx",
    "mean_abs_dy",
    "mean_dt",
    "std_dt",
    "min_dt",
    "max_dt",
]

WINDOWS = [20, 30, 50]
STEPS = [5]
CONTAMINATIONS = [0.05, 0.08, 0.10, 0.15]
N_ESTIMATORS = 500
RANDOM_STATE = 42


def make_group_id(df: pd.DataFrame) -> pd.Series:
    sid = df["sessionId"].fillna("").astype(str).str.strip()
    return np.where(
        sid != "",
        df["userIp"].astype(str) + "|" + sid,
        df["userIp"].astype(str) + "|no-session",
    )


def build_windows(df: pd.DataFrame, window: int, step: int) -> pd.DataFrame:
    df = df.copy()
    df["groupId"] = make_group_id(df)
    rows = []
    for _, g in df.groupby("groupId"):
        g = g.sort_values("requestTime").reset_index(drop=True)
        if len(g) < window:
            continue
        for start in range(0, len(g) - window + 1, step):
            w = g.iloc[start : start + window]
            x = w["x"].to_numpy()
            y = w["y"].to_numpy()
            z = w["z"].to_numpy()
            t = w["requestTime"].astype("int64").to_numpy() / 1e9
            dx = np.diff(x)
            dy = np.diff(y)
            dt = np.diff(t)
            dt = np.where(dt <= 0, 1e-6, dt)
            rows.append(
                {
                    "groupId": w["groupId"].iloc[0],
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
                }
            )
    return pd.DataFrame(rows)


def y_true_binary(labels: pd.Series) -> np.ndarray:
    return (labels == "synthetic").astype(int).to_numpy()


def y_pred_from_if(raw: np.ndarray) -> np.ndarray:
    # IF: -1 anomaly -> 1 synthetic
    return (raw == -1).astype(int)


def main() -> None:
    if not INPUT_CSV.exists():
        raise SystemExit(f"Нет файла {INPUT_CSV}. Сначала merge_raw_jsons.")

    PLOTS.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_CSV)
    df["requestTime"] = pd.to_datetime(df["requestTime"], utc=True, errors="coerce")
    for c in ("x", "y", "z"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["requestTime", "userIp", "x", "y", "z", "sourceLabel"])

    results = []

    for window in WINDOWS:
        for step in STEPS:
            wdf = build_windows(df, window=window, step=step)
            if wdf.empty:
                continue

            X = wdf[FEATURE_COLS].to_numpy()
            y = y_true_binary(wdf["sourceLabel"])
            train_mask = wdf["sourceLabel"] == "clean"

            if train_mask.sum() < 10:
                continue

            X_train = wdf.loc[train_mask, FEATURE_COLS].to_numpy()

            for contamination in CONTAMINATIONS:
                model = IsolationForest(
                    n_estimators=N_ESTIMATORS,
                    contamination=contamination,
                    random_state=RANDOM_STATE,
                )
                model.fit(X_train)

                pred_raw = model.predict(X)
                score_norm = model.score_samples(X)
                anomaly_score = -score_norm  # больше = более "аномально"

                y_hat = y_pred_from_if(pred_raw)

                prec = precision_score(y, y_hat, zero_division=0)
                rec = recall_score(y, y_hat, zero_division=0)
                f1 = f1_score(y, y_hat, zero_division=0)
                acc = accuracy_score(y, y_hat)

                try:
                    roc_auc = roc_auc_score(y, anomaly_score)
                except ValueError:
                    roc_auc = float("nan")
                try:
                    pr_auc = average_precision_score(y, anomaly_score)
                except ValueError:
                    pr_auc = float("nan")

                row = {
                    "window": window,
                    "step": step,
                    "contamination": contamination,
                    "n_windows": len(wdf),
                    "n_train_clean": int(train_mask.sum()),
                    "precision_synthetic": prec,
                    "recall_synthetic": rec,
                    "f1_synthetic": f1,
                    "accuracy": acc,
                    "roc_auc": roc_auc,
                    "pr_auc": pr_auc,
                }
                results.append(row)

    if not results:
        raise SystemExit("Нет результатов: проверьте данные и размер окон.")

    out_df = pd.DataFrame(results).sort_values(
        ["f1_synthetic", "roc_auc"], ascending=False
    )
    out_df.to_csv(OUT_CSV, index=False)
    print(f"saved: {OUT_CSV}")
    print(out_df.head(10).to_string(index=False))

    # --- графики по лучшей конфигурации (по f1_synthetic на полном переборе)
    best_row = out_df.iloc[0]
    window = int(best_row["window"])
    step = int(best_row["step"])
    contamination = float(best_row["contamination"])

    wdf = build_windows(df, window=window, step=step)
    X = wdf[FEATURE_COLS].to_numpy()
    y = y_true_binary(wdf["sourceLabel"])
    train_mask = wdf["sourceLabel"] == "clean"
    X_train = wdf.loc[train_mask, FEATURE_COLS].to_numpy()

    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=contamination,
        random_state=RANDOM_STATE,
    )
    model.fit(X_train)
    score_norm = model.score_samples(X)
    anomaly_score = -score_norm
    pred_raw = model.predict(X)
    y_hat = y_pred_from_if(pred_raw)

    fig, ax = plt.subplots(figsize=(8, 5))
    clean_s = anomaly_score[y == 0]
    syn_s = anomaly_score[y == 1]
    ax.hist(clean_s, bins=40, alpha=0.6, label="clean", density=True)
    ax.hist(syn_s, bins=40, alpha=0.6, label="synthetic", density=True)
    ax.set_xlabel("anomaly_score = -score_samples")
    ax.set_ylabel("density")
    ax.set_title(
        f"Score distribution (window={window}, step={step}, contamination={contamination})"
    )
    ax.legend()
    fig.tight_layout()
    p1 = PLOTS / "iforest_score_hist.png"
    fig.savefig(p1, dpi=150)
    plt.close(fig)

    fpr, tpr, _ = roc_curve(y, anomaly_score)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(fpr, tpr, label=f"ROC AUC = {roc_auc_score(y, anomaly_score):.4f}")
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4)
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    ax.set_title("ROC (synthetic = positive)")
    ax.legend()
    fig.tight_layout()
    p2 = PLOTS / "iforest_roc.png"
    fig.savefig(p2, dpi=150)
    plt.close(fig)

    prec_curve, rec_curve, _ = precision_recall_curve(y, anomaly_score)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(rec_curve, prec_curve, label=f"PR AUC = {average_precision_score(y, anomaly_score):.4f}")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall (synthetic = positive)")
    ax.legend()
    fig.tight_layout()
    p3 = PLOTS / "iforest_pr.png"
    fig.savefig(p3, dpi=150)
    plt.close(fig)

    report = classification_report(
        y,
        y_hat,
        target_names=["clean", "synthetic"],
        digits=4,
        zero_division=0,
    )
    (PLOTS / "iforest_classification_report.txt").write_text(
        report + "\n\n" + str(confusion_matrix(y, y_hat)),
        encoding="utf-8",
    )

    meta = {
        "best_window": window,
        "best_step": step,
        "best_contamination": contamination,
        "plots": [str(p1), str(p2), str(p3)],
        "report": str(PLOTS / "iforest_classification_report.txt"),
    }
    (PLOTS / "iforest_run_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nplots:")
    print(p1)
    print(p2)
    print(p3)


if __name__ == "__main__":
    main()
