import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.neighbors import LocalOutlierFactor
from sklearn.metrics import (
    precision_score, recall_score, f1_score, accuracy_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    roc_curve, precision_recall_curve
)

INPUT = r"C:\Users\smorozov\Desktop\NIRS\data\processed\windows_features.csv"
OUT_CSV = r"C:\Users\smorozov\Desktop\NIRS\data\processed\model_compare.csv"
OUT_DIR = r"C:\Users\smorozov\Desktop\NIRS\data\processed\plots_models"

FEATURE_COLS = [
    "req_count", "x_std", "y_std", "z_std",
    "x_unique", "y_unique", "z_unique",
    "mean_abs_dx", "mean_abs_dy",
    "mean_dt", "std_dt", "min_dt", "max_dt"
]

def to_binary(labels: pd.Series) -> np.ndarray:
    return (labels == "synthetic").astype(int).to_numpy()

def pred_to_binary(pred_raw: np.ndarray) -> np.ndarray:
    return (pred_raw == -1).astype(int)

def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\\-]+", "_", s)

def get_anomaly_score(model, X_test, y_pred_bin):
    if hasattr(model, "decision_function"):
        return -model.decision_function(X_test)
    if hasattr(model, "score_samples"):
        return -model.score_samples(X_test)
    return y_pred_bin.astype(float)

def plot_curves(model_name, y_true, anomaly_score, out_dir):
    name = safe_name(model_name)

    # ROC
    fpr, tpr, _ = roc_curve(y_true, anomaly_score)
    roc_auc = roc_auc_score(y_true, anomaly_score)
    plt.figure(figsize=(6, 6))
    plt.plot(fpr, tpr, label=f"ROC AUC = {roc_auc:.4f}")
    plt.plot([0, 1], [0, 1], "k--", alpha=0.4)
    plt.xlabel("FPR")
    plt.ylabel("TPR")
    plt.title(f"ROC — {model_name}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{out_dir}\\roc_{name}.png", dpi=150)
    plt.close()

    # PR
    p, r, _ = precision_recall_curve(y_true, anomaly_score)
    pr_auc = average_precision_score(y_true, anomaly_score)
    plt.figure(figsize=(6, 6))
    plt.plot(r, p, label=f"PR AUC = {pr_auc:.4f}")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title(f"PR — {model_name}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{out_dir}\\pr_{name}.png", dpi=150)
    plt.close()

    # Score distribution
    clean = anomaly_score[y_true == 0]
    synth = anomaly_score[y_true == 1]
    plt.figure(figsize=(8, 5))
    plt.hist(clean, bins=35, alpha=0.6, density=True, label="clean")
    plt.hist(synth, bins=35, alpha=0.6, density=True, label="synthetic")
    plt.xlabel("anomaly_score")
    plt.ylabel("density")
    plt.title(f"Score distribution — {model_name}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{out_dir}\\score_hist_{name}.png", dpi=150)
    plt.close()

def evaluate_model(name, model, X_train, X_test, y_true, out_dir):
    model.fit(X_train)
    pred_raw = model.predict(X_test)
    y_pred = pred_to_binary(pred_raw)
    anomaly_score = get_anomaly_score(model, X_test, y_pred)

    plot_curves(name, y_true, anomaly_score, out_dir)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    return {
        "model": name,
        "precision_synthetic": precision_score(y_true, y_pred, zero_division=0),
        "recall_synthetic": recall_score(y_true, y_pred, zero_division=0),
        "f1_synthetic": f1_score(y_true, y_pred, zero_division=0),
        "accuracy": accuracy_score(y_true, y_pred),
        "roc_auc": roc_auc_score(y_true, anomaly_score),
        "pr_auc": average_precision_score(y_true, anomaly_score),
        "TN": tn, "FP": fp, "FN": fn, "TP": tp,
    }

def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    df = pd.read_csv(INPUT)
    X = df[FEATURE_COLS].to_numpy()
    y = to_binary(df["sourceLabel"])

    train_mask = df["sourceLabel"] == "clean"
    X_train = df.loc[train_mask, FEATURE_COLS].to_numpy()
    X_test = X

    models = [
        ("IsolationForest", IsolationForest(n_estimators=500, contamination=0.05, random_state=42)),
        ("OneClassSVM_rbf", Pipeline([
            ("scaler", StandardScaler()),
            ("ocsvm", OneClassSVM(kernel="rbf", nu=0.05, gamma="scale"))
        ])),
        ("LOF_novelty", Pipeline([
            ("scaler", StandardScaler()),
            ("lof", LocalOutlierFactor(n_neighbors=35, contamination=0.05, novelty=True))
        ])),
    ]

    rows = []
    for name, model in models:
        rows.append(evaluate_model(name, model, X_train, X_test, y, OUT_DIR))

    out = pd.DataFrame(rows).sort_values("f1_synthetic", ascending=False)
    out.to_csv(OUT_CSV, index=False)

    # Общий график сравнения F1
    plt.figure(figsize=(7, 4))
    plt.bar(out["model"], out["f1_synthetic"])
    plt.ylim(0, 1)
    plt.ylabel("F1 (synthetic)")
    plt.title("Model comparison by F1")
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}\\models_f1_compare.png", dpi=150)
    plt.close()

    print("saved table:", OUT_CSV)
    print("saved plots:", OUT_DIR)
    print(out.to_string(index=False))

if __name__ == "__main__":
    main()