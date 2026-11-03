"""Поиск оптимального временного окна для детектора несанкционированного скачивания.

Расширение исследования из Tutorial.ipynb: в статье результаты получены для окна
20 запросов со сдвигом 5. Здесь перебирается сетка размеров окна (10..50, шаг 5)
и сдвигов (1..10, шаг 1) для трёх моделей: Isolation Forest, One-Class SVM, LOF.

Два этапа:
  screen — все 81 комбинация, гиперпараметры зафиксированы на значениях из статьи,
           метрика порога не подбирается (ROC-AUC / PR-AUC на внешних блоках).
           Дёшево, даёт картину поверхности «окно × сдвиг».
  full   — полный протокол статьи (вложенная кросс-валидация: подбор
           гиперпараметров по ROC-AUC на внутренних блоках + подбор порога q по F1)
           для выбранных комбинаций (--all либо --top N по результатам screen).

Протокол оценки полностью повторяет статью: внешняя StratifiedGroupKFold
(группа — сегмент сеанса), модели обучаются только на легитимных окнах,
порог калибруется по оценкам «вне выборки» (cross-fitting по CALIB_FOLDS блокам).

Результаты каждой комбинации пишутся в отдельный CSV (результаты не теряются
при обрыве), сводка и тепловые карты — командой aggregate. По итогам full
формируются отчёт window_search_report_full.xlsx (лист на модель + лист
«Лучшие результаты») и иллюстрации для лучшей комбинации каждой модели
(ROC/PR-кривые, гистограмма аномальности) в best_figures/.

Примеры:
  python window_search.py screen                       # скрининг всех 81 комбинации
  python window_search.py full --top 5                 # полный подбор для топ-5 на модель
  python window_search.py full --all --jobs 4          # полный подбор для всех 81 (долго)
  python window_search.py aggregate                    # сводные таблицы и тепловые карты
  python window_search.py report                       # xlsx-отчёт и иллюстрации по full
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, ParameterGrid, StratifiedGroupKFold
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# 0. Параметры эксперимента (как в Tutorial.ipynb)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "tmp_files"
OUT_DIR = DATA_DIR / "window_search"
WINDOWS_DIR = OUT_DIR / "windows"

RAW_FILES = [
    (DATA_DIR / "requests_raw_clean.json", "clean"),
    (DATA_DIR / "requests_raw_synthetic.json", "synthetic"),
]
MERGED_CSV = DATA_DIR / "requests_merged_labeled.csv"

SESSION_GAP = pd.Timedelta(minutes=30)
MAX_SESSION_REQUESTS = 200

WINDOW_GRID = list(range(10, 51, 5))   # размер окна, запросов
STEP_GRID = list(range(1, 11))         # сдвиг окна, запросов

N_OUTER = 5
N_INNER = 3
RANDOM_STATE = 42
CALIB_FOLDS = 4

Q_GRID = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]

FEATURE_COLS = [
    "req_count", "x_std", "y_std", "z_std",
    "x_unique", "y_unique", "z_unique",
    "mean_abs_dx", "mean_abs_dy",
    "mean_dt", "std_dt", "min_dt", "max_dt",
]

MODEL_NAMES = ["Isolation Forest", "One-Class SVM", "LOF"]
N_TREES = 200

PARAM_GRIDS = {
    "Isolation Forest": {
        "max_samples": ["auto", 0.1, 0.25, 0.5, 0.75, 1.0],
    },
    "One-Class SVM": {
        "gamma": [0.001, 0.003, 0.01, 0.03, round(1 / 12, 3), 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0],
        "nu": [0.01, 0.02, 0.05, 0.1, 0.2],
    },
    "LOF": {
        "n_neighbors": [10, 20, 25, 35, 40, 45, 50, 100],
    },
}

# Фиксированные гиперпараметры для этапа screen (выбранные в статье для окна 20/5)
SCREEN_PARAMS = {
    "Isolation Forest": {"max_samples": 1.0},
    "One-Class SVM": {"gamma": 10.0, "nu": 0.02},
    "LOF": {"n_neighbors": 35},
}

METRICS = ["Precision", "Recall", "F1", "Accuracy", "ROC-AUC", "PR-AUC"]


# ---------------------------------------------------------------------------
# 1. Загрузка и выделение сеансов (как в Tutorial.ipynb, разделы 1–2)
# ---------------------------------------------------------------------------

def load_requests() -> pd.DataFrame:
    if MERGED_CSV.exists():
        df = pd.read_csv(MERGED_CSV, parse_dates=["requestTime"])
        return df

    rows = []
    for path, label in RAW_FILES:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            s = item.get("_source", item)
            rows.append({
                "requestTime": s.get("requestTime"),
                "userIp": s.get("userIp"),
                "x": s.get("x"),
                "y": s.get("y"),
                "z": s.get("z"),
                "sourceLabel": label,
            })
    df = pd.DataFrame(rows)
    df["requestTime"] = pd.to_datetime(df["requestTime"], errors="coerce", utc=True, format="mixed")
    for c in ["x", "y", "z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["requestTime", "userIp", "x", "y", "z"]).reset_index(drop=True)

    df = df.sort_values(["sourceLabel", "userIp", "requestTime"]).reset_index(drop=True)
    new_session = df.groupby(["sourceLabel", "userIp"])["requestTime"].diff() > SESSION_GAP
    df["sessionNo"] = new_session.groupby([df["sourceLabel"], df["userIp"]]).cumsum().astype(int)
    raw_key = df["sourceLabel"] + "|" + df["userIp"].astype(str) + "|" + df["sessionNo"].astype(str)
    seg_no = df.groupby(raw_key).cumcount() // MAX_SESSION_REQUESTS
    df["sessionKey"] = raw_key + "|" + seg_no.astype(str)
    return df


def load_or_build_windows(df: pd.DataFrame, window: int, step: int) -> pd.DataFrame:
    """Окна кешируются в CSV, чтобы повторные запуски не строили их заново."""
    WINDOWS_DIR.mkdir(parents=True, exist_ok=True)
    cache = WINDOWS_DIR / f"windows_w{window}_s{step}.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["startTime", "endTime"])
    wdf = build_windows(df, window=window, step=step)
    wdf.to_csv(cache, index=False)
    return wdf


# ---------------------------------------------------------------------------
# 2. Построение окон и признаков (как в Tutorial.ipynb, раздел 3)
# ---------------------------------------------------------------------------

def build_windows(df_in: pd.DataFrame, window: int, step: int) -> pd.DataFrame:
    rows = []
    for key, g in df_in.groupby("sessionKey"):
        g = g.sort_values("requestTime").reset_index(drop=True)
        if len(g) < window:
            continue
        for i in range(0, len(g) - window + 1, step):
            w = g.iloc[i:i + window]
            x = w["x"].to_numpy()
            y = w["y"].to_numpy()
            z = w["z"].to_numpy()
            t = (w["requestTime"] - w["requestTime"].iloc[0]).dt.total_seconds().to_numpy()

            dx = np.diff(x)
            dy = np.diff(y)
            dt = np.diff(t)
            dt = np.where(dt <= 0, 1e-6, dt)

            rows.append({
                "sessionKey": key,
                "userIp": w["userIp"].iloc[0],
                "startTime": w["requestTime"].iloc[0],
                "endTime": w["requestTime"].iloc[-1],
                "sourceLabel": w["sourceLabel"].iloc[0],
                "req_count": len(w),
                "x_std": float(np.std(x)), "y_std": float(np.std(y)), "z_std": float(np.std(z)),
                "x_unique": int(len(np.unique(x))), "y_unique": int(len(np.unique(y))), "z_unique": int(len(np.unique(z))),
                "mean_abs_dx": float(np.mean(np.abs(dx))),
                "mean_abs_dy": float(np.mean(np.abs(dy))),
                "mean_dt": float(np.mean(dt)),
                "std_dt": float(np.std(dt)),
                "min_dt": float(np.min(dt)),
                "max_dt": float(np.max(dt)),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Модели и подбор (как в Tutorial.ipynb, разделы 4–5)
# ---------------------------------------------------------------------------

def build_model(name: str, params: dict, random_state: int = RANDOM_STATE):
    if name == "Isolation Forest":
        return IsolationForest(random_state=random_state, n_jobs=-1, **{"n_estimators": N_TREES, **params})
    if name == "One-Class SVM":
        return Pipeline([("scaler", StandardScaler()),
                         ("model", OneClassSVM(kernel="rbf", **params))])
    if name == "LOF":
        return Pipeline([("scaler", StandardScaler()),
                         ("model", LocalOutlierFactor(novelty=True, metric="euclidean", **params))])
    raise ValueError(name)


def anomaly_score(model, X_: np.ndarray) -> np.ndarray:
    return -model.decision_function(X_)


def grid_for(name: str, n_train_clean: int):
    grid = list(ParameterGrid(PARAM_GRIDS[name]))
    if name == "LOF":  # k должно быть меньше числа обучающих объектов
        grid = [p for p in grid if p["n_neighbors"] < n_train_clean] or [{"n_neighbors": max(1, n_train_clean - 1)}]
    return grid


def make_group_cv(y_: np.ndarray, groups_: np.ndarray, n_splits: int, seed: int):
    per_class = pd.Series(groups_).groupby(y_).nunique()
    if len(per_class) < 2:
        raise ValueError("В выборке присутствует только один класс")
    k = int(min(n_splits, per_class.min()))
    if k < 2:
        raise ValueError(f"Недостаточно сеансов для групповой кросс-валидации: {per_class.to_dict()}")
    cv = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
    return [(a, b) for a, b in cv.split(np.zeros(len(y_)), y_, groups_) if len(np.unique(y_[b])) == 2]


def threshold_from_q(calib_clean_scores: np.ndarray, q: float) -> float:
    return float(np.quantile(calib_clean_scores, 1 - q))


def fit_calibrated(name: str, params: dict, X_clean: np.ndarray, g_clean: np.ndarray, calibrate: bool = True):
    model = build_model(name, params).fit(X_clean)
    if not calibrate:
        return model, None
    k = min(CALIB_FOLDS, len(np.unique(g_clean)))
    oof_scores = np.empty(len(X_clean))
    for fit_idx, cal_idx in GroupKFold(n_splits=k).split(X_clean, groups=g_clean):
        m = build_model(name, params).fit(X_clean[fit_idx])
        oof_scores[cal_idx] = anomaly_score(m, X_clean[cal_idx])
    return model, oof_scores


def tune(name: str, X_tr: np.ndarray, y_tr: np.ndarray, g_tr: np.ndarray, seed: int = RANDOM_STATE):
    splits = make_group_cv(y_tr, g_tr, N_INNER, seed)
    if not splits:
        raise ValueError("Во внутренней кросс-валидации нет блоков с обоими классами")

    # Этап 1: гиперпараметры по ROC-AUC
    min_clean = int(min((y_tr[a] == 0).sum() for a, _ in splits) * (1 - 1 / CALIB_FOLDS) * 0.9)
    grid = grid_for(name, min_clean)
    records = []
    for params in grid:
        aucs = []
        for a, b in splits:
            m, _ = fit_calibrated(name, params, X_tr[a][y_tr[a] == 0], g_tr[a][y_tr[a] == 0], calibrate=False)
            aucs.append(roc_auc_score(y_tr[b], anomaly_score(m, X_tr[b])))
        records.append({**params, "roc_auc_mean": np.mean(aucs), "roc_auc_std": np.std(aucs)})
    table = pd.DataFrame(records)
    best_idx = int(table["roc_auc_mean"].idxmax())
    best_params = grid[best_idx]

    # Этап 2: порог (доля q) по F1 при выбранных гиперпараметрах
    cache = []
    for a, b in splits:
        m, s_cal = fit_calibrated(name, best_params, X_tr[a][y_tr[a] == 0], g_tr[a][y_tr[a] == 0])
        cache.append((s_cal, anomaly_score(m, X_tr[b]), y_tr[b]))
    f1_by_q = {q: np.mean([f1_score(yb, (sb > threshold_from_q(sa, q)).astype(int), zero_division=0)
                           for sa, sb, yb in cache])
               for q in Q_GRID}
    best_q = max(f1_by_q, key=f1_by_q.get)
    return best_params, best_q, table, f1_by_q


# ---------------------------------------------------------------------------
# 4. Оценка одной комбинации (окно, сдвиг)
# ---------------------------------------------------------------------------

def evaluate_config(df: pd.DataFrame, window: int, step: int, mode: str) -> pd.DataFrame:
    """Вложенная оценка для одной комбинации. Возвращает таблицу по внешним блокам.

    mode="screen": гиперпараметры фиксированы (SCREEN_PARAMS), порог не подбирается,
                   считаются только порогонезависимые метрики (ROC-AUC, PR-AUC).
    mode="full":   полный протокол статьи (подбор гиперпараметров и порога).
    """
    wdf = load_or_build_windows(df, window, step)
    if wdf.empty:
        raise ValueError("Ни один сеанс не дал окон")

    X = wdf[FEATURE_COLS].to_numpy(dtype=float)
    y = (wdf["sourceLabel"] == "synthetic").astype(int).to_numpy()
    groups = wdf["sessionKey"].to_numpy()

    outer_splits = make_group_cv(y, groups, N_OUTER, RANDOM_STATE)
    if not outer_splits:
        raise ValueError("Во внешней кросс-валидации нет блоков с обоими классами")

    fold_rows, chosen_rows = [], []
    oof = {name: [] for name in MODEL_NAMES}   # данные для ROC/PR-кривых и гистограмм
    for fold, (tr, te) in enumerate(outer_splits):
        X_tr, y_tr, g_tr = X[tr], y[tr], groups[tr]
        X_te, y_te = X[te], y[te]
        X_tr_clean, g_tr_clean = X_tr[y_tr == 0], g_tr[y_tr == 0]

        for name in MODEL_NAMES:
            if mode == "screen":
                params, q = SCREEN_PARAMS[name], None
                model, _ = fit_calibrated(name, params, X_tr_clean, g_tr_clean, calibrate=False)
                s_te = anomaly_score(model, X_te)
                tn = fp = fn = tp = np.nan
                prec = rec = f1 = acc = np.nan
            else:
                params, q, _, _ = tune(name, X_tr, y_tr, g_tr)
                model, s_cal = fit_calibrated(name, params, X_tr_clean, g_tr_clean)
                thr = threshold_from_q(s_cal, q)
                s_te = anomaly_score(model, X_te)
                scale = np.std(s_cal) if np.std(s_cal) > 0 else 1.0
                oof[name].append({"y": y_te, "s": s_te, "thr": thr, "scale": scale})
                y_pred = (s_te > thr).astype(int)
                tn, fp, fn, tp = confusion_matrix(y_te, y_pred, labels=[0, 1]).ravel()
                prec = precision_score(y_te, y_pred, zero_division=0)
                rec = recall_score(y_te, y_pred, zero_division=0)
                f1 = f1_score(y_te, y_pred, zero_division=0)
                acc = accuracy_score(y_te, y_pred)

            fold_rows.append({
                "window": window, "step": step, "Модель": name, "fold": fold,
                "n_windows": len(wdf), "n_groups": len(np.unique(groups)),
                "Precision": prec, "Recall": rec, "F1": f1, "Accuracy": acc,
                "ROC-AUC": roc_auc_score(y_te, s_te),
                "PR-AUC": average_precision_score(y_te, s_te),
                "TN": tn, "FP": fp, "FN": fn, "TP": tp,
            })
            chosen_rows.append({"window": window, "step": step, "Модель": name, "fold": fold,
                                "params": json.dumps(params, ensure_ascii=False), "q": q})

    if mode == "full":
        # оценки тестовых блоков для ROC/PR-кривых и гистограмм аномальности
        joblib.dump(oof, OUT_DIR / f"oof_{mode}_w{window}_s{step}.joblib")

    return pd.DataFrame(fold_rows), pd.DataFrame(chosen_rows)


def result_path(stage: str, window: int, step: int) -> Path:
    return OUT_DIR / f"res_{stage}_w{window}_s{step}.csv"


def run_configs(df: pd.DataFrame, configs: list[tuple[int, int]], mode: str, jobs: int) -> None:
    todo = [(w, s) for w, s in configs if not result_path(mode, w, s).exists()]
    skipped = len(configs) - len(todo)
    if skipped:
        print(f"Уже посчитано: {skipped}, осталось: {len(todo)}")

    def one(cfg):
        w, s = cfg
        t0 = time.time()
        try:
            folds_df, chosen_df = evaluate_config(df, w, s, mode)
        except Exception as e:  # комбинация непригодна (мало сеансов и т.п.) — фиксируем и идём дальше
            folds_df = pd.DataFrame([{"window": w, "step": s, "Модель": None, "fold": None,
                                      "error": f"{type(e).__name__}: {e}"}])
            chosen_df = pd.DataFrame()
        folds_df.to_csv(result_path(mode, w, s), index=False)
        if len(chosen_df):
            chosen_df.to_csv(OUT_DIR / f"chosen_{mode}_w{w}_s{s}.csv", index=False)
        return w, s, time.time() - t0, folds_df

    if jobs and jobs > 1:
        from joblib import Parallel, delayed
        results = Parallel(n_jobs=jobs, verbose=5)(delayed(one)(c) for c in todo)
    else:
        results = []
        for i, cfg in enumerate(todo):
            w, s, dt, folds_df = one(cfg)
            results.append((w, s, dt, folds_df))
            done = i + 1
            eta = np.mean([r[2] for r in results]) * (len(todo) - done)
            auc_msg = ""
            ok = folds_df["Модель"].notna() if len(folds_df) else False
            if ok.any():
                m = folds_df[ok].groupby("Модель")["ROC-AUC"].mean().round(3).to_dict()
                auc_msg = ", ROC-AUC: " + ", ".join(f"{k}={v}" for k, v in m.items())
            print(f"[{done}/{len(todo)}] окно {w}, сдвиг {s}: {dt:.1f} с{auc_msg}; "
                  f"ETA {eta / 60:.1f} мин", flush=True)

    errors = [(w, s) for w, s, _, f in results if len(f) and f["Модель"].isna().all()]
    if errors:
        print("Комбинации с ошибками (см. колонку error в CSV):", errors)


def collect(stage: str) -> pd.DataFrame:
    files = sorted(OUT_DIR.glob(f"res_{stage}_w*_s*.csv"))
    if not files:
        raise SystemExit(f"Нет результатов этапа '{stage}' в {OUT_DIR}")
    parts = [pd.read_csv(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df["cfg"] = df["window"].astype(str) + "/" + df["step"].astype(str)
    return df


# ---------------------------------------------------------------------------
# 5. Сводка и тепловые карты
# ---------------------------------------------------------------------------

def aggregate(stage: str) -> None:
    import matplotlib.pyplot as plt

    folds_df = collect(stage)
    folds_df = folds_df[folds_df["Модель"].notna()].copy()
    for c in ["window", "step"]:
        folds_df[c] = folds_df[c].astype(int)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    folds_df.to_csv(OUT_DIR / f"all_folds_{stage}.csv", index=False)

    summary = folds_df.groupby(["Модель", "window", "step"], sort=True)[METRICS].agg(["mean", "std"])
    summary.to_csv(OUT_DIR / f"summary_{stage}.csv")

    print(f"=== Сводка по этапу '{stage}' (среднее по {N_OUTER} внешним блокам) ===")
    for name in MODEL_NAMES:
        sub = summary.loc[name]
        best = sub[("ROC-AUC", "mean")].idxmax()
        print(f"\n{name}: лучшая комбинация окно={best[0]}, сдвиг={best[1]} "
              f"(ROC-AUC {sub.loc[best, ('ROC-AUC', 'mean')]:.3f} ± {sub.loc[best, ('ROC-AUC', 'std')]:.3f})")
        top = sub.sort_values(("ROC-AUC", "mean"), ascending=False).head(10)
        print(top[[("ROC-AUC", "mean"), ("ROC-AUC", "std"), ("PR-AUC", "mean"), ("F1", "mean")]]
              .rename(columns={"ROC-AUC": "ROC-AUC", "PR-AUC": "PR-AUC"}).round(3).to_string())

    # тепловые карты ROC-AUC и F1: строки — размер окна, столбцы — сдвиг
    for metric in ["ROC-AUC", "F1"]:
        fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
        for ax, name in zip(axes, MODEL_NAMES):
            pivot = summary.loc[name][(metric, "mean")].reset_index() \
                .pivot(index="window", columns="step", values=(metric, "mean")) \
                .reindex(index=WINDOW_GRID, columns=STEP_GRID)
            im = ax.imshow(pivot.to_numpy(), origin="lower", aspect="auto", cmap="viridis")
            ax.set_xticks(range(len(STEP_GRID)), STEP_GRID)
            ax.set_yticks(range(len(WINDOW_GRID)), WINDOW_GRID)
            ax.set_xlabel("Сдвиг окна"); ax.set_ylabel("Размер окна")
            ax.set_title(f"{name}")
            for i in range(len(WINDOW_GRID)):
                for j in range(len(STEP_GRID)):
                    v = pivot.to_numpy()[i, j]
                    if not np.isnan(v):
                        ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                                fontsize=7, color="white" if v < pivot.to_numpy().mean() else "black")
            fig.colorbar(im, ax=ax, shrink=0.85)
        fig.suptitle(f"{metric}: среднее по внешним блокам")
        fig.tight_layout()
        fig.savefig(OUT_DIR / f"heatmap_{metric.replace('-', '_').lower()}_{stage}.png", dpi=300)
        print(f"Сохранено: {OUT_DIR / f'heatmap_{metric.replace('-', '_').lower()}_{stage}.png'}")
    plt.close("all")

    # пересчёт выбранных гиперпараметров для этапа full
    if stage == "full":
        chosen_files = sorted(OUT_DIR.glob("chosen_full_w*_s*.csv"))
        if chosen_files:
            chosen = pd.concat([pd.read_csv(f) for f in chosen_files], ignore_index=True)
            chosen.to_csv(OUT_DIR / "chosen_full.csv", index=False)
            print("\n=== Устойчивость выбранных гиперпараметров ===")
            for name in MODEL_NAMES:
                sub = chosen[chosen["Модель"] == name]
                freq = sub.groupby(["window", "step"])["params"].agg(
                    lambda p: pd.Series(p).value_counts().iloc[0] / len(p))
                print(f"\n{name} — доля блоков, где выбраны самые частые параметры:")
                print(freq.rename("доля блоков").round(2).to_string())


# ---------------------------------------------------------------------------
# 6. Отчёт в xlsx для этапа full
# ---------------------------------------------------------------------------

REPORT_METRICS = ["Accuracy", "Precision", "Recall", "F1", "ROC-AUC", "PR-AUC"]


def _means_by_config(stage: str) -> pd.DataFrame:
    folds_df = collect(stage)
    folds_df = folds_df[folds_df["Модель"].notna()].copy()
    for c in ["window", "step"]:
        folds_df[c] = folds_df[c].astype(int)
    return folds_df.groupby(["Модель", "window", "step"], sort=True)[REPORT_METRICS].mean().reset_index()


def _best_rows(means: pd.DataFrame) -> pd.DataFrame:
    """Лучшая комбинация для каждой модели: максимум ROC-AUC, при равенстве — F1."""
    rows = []
    for name in MODEL_NAMES:
        sub = means[means["Модель"] == name]
        best = sub.sort_values(["ROC-AUC", "F1"], ascending=False).iloc[0]
        rows.append({"Модель": name, "window": int(best["window"]), "step": int(best["step"]),
                     **{m: float(best[m]) for m in REPORT_METRICS}})
    return pd.DataFrame(rows)


def _load_chosen(stage: str) -> pd.DataFrame:
    single = OUT_DIR / f"chosen_{stage}.csv"
    files = [single] if single.exists() else sorted(OUT_DIR.glob(f"chosen_{stage}_w*_s*.csv"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def _fmt_params(s: str) -> str:
    try:
        parsed = json.loads(s)
    except (ValueError, TypeError):
        return str(s)
    if isinstance(parsed, dict):
        return ", ".join(f"{k}={v}" for k, v in parsed.items())
    return str(parsed)


def _majority(series: pd.Series) -> str:
    vc = series.dropna().astype(str).value_counts()
    return f"{_fmt_params(vc.index[0])} ({vc.iloc[0]}/{vc.sum()} блоков)" if len(vc) else "—"


def report_xlsx(stage: str = "full") -> Path:
    """Отчёт: лист на каждый классификатор (метрики, усреднённые по внешним блокам,
    для всех комбинаций окно/сдвиг) + лист с наилучшей комбинацией по каждому
    классификатору (критерий — ROC-AUC, при равенстве — F1) с гиперпараметрами."""
    folds_df = collect(stage)
    folds_df = folds_df[folds_df["Модель"].notna()].copy()
    for c in ["window", "step"]:
        folds_df[c] = folds_df[c].astype(int)

    means = folds_df.groupby(["Модель", "window", "step"], sort=True)[REPORT_METRICS].mean().reset_index()
    chosen = _load_chosen(stage)

    out_path = OUT_DIR / f"window_search_report_{stage}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        best_rows = []
        for name in MODEL_NAMES:
            sub = means[means["Модель"] == name].sort_values(["window", "step"])
            sheet = (sub.rename(columns={"window": "Window", "step": "STEP"})[["Window", "STEP", *REPORT_METRICS]])
            sheet.to_excel(xw, sheet_name=name, index=False)

            sub = sub.copy()
            best = sub.sort_values(["ROC-AUC", "F1"], ascending=False).iloc[0]
            cfg = chosen[(chosen["Модель"] == name)
                         & (chosen["window"] == best["window"]) & (chosen["step"] == best["step"])]
            best_rows.append({
                "Модель": name,
                "Window": int(best["window"]),
                "STEP": int(best["step"]),
                **{m: round(float(best[m]), 4) for m in REPORT_METRICS},
                "Гиперпараметры": _majority(cfg["params"]) if len(cfg) else "—",
                "q": _majority(cfg["q"]) if len(cfg) else "—",
            })
        pd.DataFrame(best_rows).to_excel(xw, sheet_name="Лучшие результаты", index=False)

    print(f"Отчёт сохранён: {out_path}")
    return out_path


    folds_df = collect(stage)
    folds_df = folds_df[folds_df["Модель"].notna()].copy()
    for c in ["window", "step"]:
        folds_df[c] = folds_df[c].astype(int)

    means = folds_df.groupby(["Модель", "window", "step"], sort=True)[REPORT_METRICS].mean().reset_index()
    chosen = _load_chosen(stage)

    out_path = OUT_DIR / f"window_search_report_{stage}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for name in MODEL_NAMES:
            sub = means[means["Модель"] == name].sort_values(["window", "step"])
            sheet = (sub.rename(columns={"window": "Window", "step": "STEP"})[["Window", "STEP", *REPORT_METRICS]])
            sheet.to_excel(xw, sheet_name=name, index=False)

        best_rows = []
        for _, best in _best_rows(means).iterrows():
            name = best["Модель"]
            cfg = chosen[(chosen["Модель"] == name)
                         & (chosen["window"] == best["window"]) & (chosen["step"] == best["step"])]
            best_rows.append({
                "Модель": name,
                "Window": best["window"],
                "STEP": best["step"],
                **{m: round(float(best[m]), 4) for m in REPORT_METRICS},
                "Гиперпараметры": _majority(cfg["params"]) if len(cfg) else "—",
                "q": _majority(cfg["q"]) if len(cfg) else "—",
            })
        pd.DataFrame(best_rows).to_excel(xw, sheet_name="Лучшие результаты", index=False)

    print(f"Отчёт сохранён: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# 7. Иллюстрации для лучшей комбинации каждой модели (ROC/PR-кривые,
#    гистограмма аномальности) — в стиле разделов 6–7 Tutorial.ipynb
# ---------------------------------------------------------------------------

def plot_best_illustrations(stage: str = "full") -> None:
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator
    from sklearn.metrics import precision_recall_curve, roc_curve

    means = _means_by_config(stage)
    best = _best_rows(means).set_index("Модель")

    CM = 1 / 2.54
    FIG_SIZE = (8.5 * CM, 6.8 * CM)          # ширина одной колонки
    plt.rcParams.update({
        "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
        "legend.fontsize": 7, "legend.title_fontsize": 7, "lines.linewidth": 1.4,
        "axes.linewidth": 0.6, "grid.linewidth": 0.4, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })
    COLORS = {"Isolation Forest": "tab:blue", "One-Class SVM": "tab:green", "LOF": "tab:red"}
    LINESTYLES = {"Isolation Forest": "-", "One-Class SVM": "--", "LOF": "-."}
    LABELS = {"Isolation Forest": "Isolation Forest", "One-Class SVM": "SVM", "LOF": "LOF"}
    COMMA = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−"))

    def band(ax, x, curves, name):
        # разброс ± одно стандартное отклонение по внешним блокам
        m, sd = np.mean(curves, axis=0), np.std(curves, axis=0)
        lo, hi = np.clip(m - sd, 0, 1), np.clip(m + sd, 0, 1)
        ax.fill_between(x, lo, hi, color=COLORS[name], alpha=0.10, lw=0, zorder=1)
        for b in (lo, hi):
            ax.plot(x, b, color=COLORS[name], ls=LINESTYLES[name], lw=0.4, alpha=0.6, zorder=2)
        return m

    def finish(fig, ax, path):
        ax.xaxis.set_major_formatter(COMMA)
        ax.yaxis.set_major_formatter(COMMA)
        ax.grid(alpha=0.3)
        fig.savefig(path.with_suffix(".png"), dpi=600)
        fig.savefig(path.with_suffix(".pdf"))
        plt.close(fig)

    figs_dir = OUT_DIR / "best_figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    grid = np.linspace(0, 1, 501)

    for name in MODEL_NAMES:
        w, s = int(best.loc[name, "window"]), int(best.loc[name, "step"])
        oof_path = OUT_DIR / f"oof_{stage}_w{w}_s{s}.joblib"
        if not oof_path.exists():
            print(f"Нет OOF-оценок для {name} (окно {w}, сдвиг {s}) — пропуск иллюстраций")
            continue
        oof = joblib.load(oof_path)[name]
        stem = f"{LABELS[name].replace(' ', '_')}_w{w}_s{s}"
        auc_m, ap_m = best.loc[name, "ROC-AUC"], best.loc[name, "PR-AUC"]

        # ROC
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        tprs = []
        for f in oof:
            fpr, tpr, _ = roc_curve(f["y"], f["s"])
            t = np.interp(grid, fpr, tpr)
            t[0] = 0.0
            tprs.append(t)
        m = band(ax, grid, tprs, name)
        ax.plot(grid, m, color=COLORS[name], ls=LINESTYLES[name], zorder=3,
                label=f"{LABELS[name]}: {auc_m:.3f}".replace(".", ","))
        ax.plot([0, 1], [0, 1], color="gray", lw=0.8, ls=":", label="Случайный: 0,5")
        ax.set(xlim=(0, 1), ylim=(0, 1.02), xlabel="Доля ложных срабатываний (FPR)",
               ylabel="Доля обнаружений (TPR)")
        ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ax.yaxis.set_major_locator(MultipleLocator(0.2))
        ax.legend(title="ROC-AUC", loc="lower right", frameon=True, framealpha=0.9)
        finish(fig, ax, figs_dir / f"roc_{stem}")

        # PR
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        precs = []
        for f in oof:
            p, r, _ = precision_recall_curve(f["y"], f["s"])
            precs.append(np.interp(grid, r[::-1], p[::-1]))
        m = band(ax, grid, precs, name)
        ax.plot(grid, m, color=COLORS[name], ls=LINESTYLES[name], zorder=3,
                label=f"{LABELS[name]}: {ap_m:.3f}".replace(".", ","))
        prevalence = float(np.concatenate([f["y"] for f in oof]).mean())
        ax.axhline(prevalence, color="gray", lw=0.8, ls=":",
                   label=f"Случайный: {prevalence:.2f}".replace(".", ","))
        ax.set(xlim=(0, 1), ylim=(0, 1.02), xlabel="Полнота (Recall)", ylabel="Точность (Precision)")
        ax.xaxis.set_major_locator(MultipleLocator(0.2))
        ax.yaxis.set_major_locator(MultipleLocator(0.2))
        ax.legend(title="PR-AUC", loc="lower left", frameon=True, framealpha=0.9)
        finish(fig, ax, figs_dir / f"pr_{stem}")

        # Гистограмма аномальности (z = (оценка − порог) / ст. отклонение OOF-оценок)
        fig, ax = plt.subplots(figsize=(FIG_SIZE[0], 7.5 * CM))
        yy = np.concatenate([f["y"] for f in oof])
        zz = np.concatenate([(f["s"] - f["thr"]) / f["scale"] for f in oof])
        t = np.sign(zz) * np.log1p(np.abs(zz))
        bt = np.linspace(t.min(), t.max(), 41)
        bins = np.sign(bt) * np.expm1(np.abs(bt))
        ax.hist(zz[yy == 0], bins=bins, color="tab:blue", alpha=0.6, label="Легитимные")
        ax.hist(zz[yy == 1], bins=bins, color="tab:red", alpha=0.45, hatch="////",
                edgecolor="tab:red", linewidth=0.3, label="Нелегитимные")
        ax.axvline(0, color="black", ls="--", lw=1.0, label="Порог")
        ax.set_xscale("symlog", linthresh=1, linscale=0.6)
        ticks = [-30, -10, -5, -2, -1, -0.5, 0, 0.5, 1, 2, 5, 10, 30, 100]
        ax.set_xticks([v for v in ticks if bins[0] <= v <= bins[-1]])
        ax.set_xlim(bins[0], bins[-1])
        ax.set_xlabel("Нормированная оценка аномальности z")
        ax.set_ylabel("Число окон")
        ax.xaxis.set_major_formatter(COMMA)
        ax.yaxis.set_major_formatter(COMMA)
        ax.grid(alpha=0.3, axis="y")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.22)
        ax.legend(loc="upper center", ncol=3, frameon=False, handlelength=1.6,
                  columnspacing=1.0, borderaxespad=0.3)
        finish(fig, ax, figs_dir / f"hist_{stem}")

        print(f"{name}: иллюстрации для окна {w}, сдвига {s} → {figs_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["screen", "full", "aggregate", "report"])
    ap.add_argument("--all", action="store_true", help="full: все 81 комбинация")
    ap.add_argument("--top", type=int, default=None, help="full: топ-N комбинаций на модель по screen")
    ap.add_argument("--windows", type=str, default=None, help="список размеров окна, напр. 15,20,25")
    ap.add_argument("--steps", type=str, default=None, help="список сдвигов, напр. 2,5")
    ap.add_argument("--jobs", type=int, default=1, help="число параллельных воркеров")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "aggregate":
        aggregate("full" if list(OUT_DIR.glob("res_full_w*_s*.csv")) else "screen")
        return

    if args.command == "report":
        report_xlsx("full")
        plot_best_illustrations("full")
        return

    df = load_requests()

    if args.windows:
        windows = [int(v) for v in args.windows.split(",")]
    else:
        windows = WINDOW_GRID
    if args.steps:
        steps = [int(v) for v in args.steps.split(",")]
    else:
        steps = STEP_GRID
    configs = [(w, s) for w in windows for s in steps if s < w]
    if not configs:
        raise SystemExit("Пустая сетка комбинаций")

    if args.command == "screen":
        run_configs(df, configs, mode="screen", jobs=args.jobs)
        aggregate("screen")
        return

    # full
    if args.all:
        todo = configs
    elif args.top:
        screen = collect("screen")
        screen = screen[screen["Модель"].notna()]
        means = screen.groupby(["Модель", "window", "step"])["ROC-AUC"].mean()
        picks = set()
        for name in MODEL_NAMES:
            top = means.loc[name].sort_values(ascending=False).head(args.top)
            picks.update((int(w), int(s)) for w, s in top.index)
        picks.add((20, 5))  # базовая конфигурация статьи — всегда для сопоставимости
        todo = [(w, s) for w, s in configs if (w, s) in picks]
        print(f"Полный подбор для {len(todo)} комбинаций: {sorted(todo)}")
    else:
        todo = configs  # по умолчанию — указанные через --windows/--steps

    run_configs(df, todo, mode="full", jobs=args.jobs)
    aggregate("full")
    report_xlsx("full")
    plot_best_illustrations("full")


if __name__ == "__main__":
    main()
