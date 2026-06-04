# Local Outlier Factor (novelty mode)

**Файл:** `scripts/ml/compare_classic_models.py`

```python
Pipeline([
    ("scaler", StandardScaler()),
    ("lof", LocalOutlierFactor(n_neighbors=35, contamination=0.05, novelty=True)),
])
```

| Параметр | Значение |
|---|---|
| Препроцессинг | `StandardScaler` |
| `n_neighbors` (k) | 35 |
| `contamination` | 0.05 |
| `novelty` | `True` (используется `predict` для новых точек) |
| Обучающая выборка | только `sourceLabel == "clean"` |

## Идея модели

LOF сравнивает **локальную плотность** точки с локальной плотностью её соседей.
Если у `x` плотность заметно ниже, чем у его `k` ближайших соседей в обучающей
выборке, то LOF(x) > 1 — точка считается аномальной.

Ключевые величины:

- `N_k(x)` — множество k ближайших соседей точки `x`;
- `reach-dist_k(x, o) = max(d_k(o), d(x, o))` — reachability distance;
- `lrd_k(x) = 1 / mean_{o ∈ N_k(x)} reach-dist_k(x, o)` — локальная плотность;
- `LOF_k(x) = mean_{o ∈ N_k(x)} (lrd_k(o) / lrd_k(x))`.

## Диаграмма «слоёв» pipeline-а

```mermaid
flowchart TB
    X["Вход: x ∈ ℝ¹³"]
    X --> SC["Слой 1: StandardScaler<br/>z = (x − μ) / σ"]
    SC --> KNN["Слой 2: kNN-поиск<br/>N_k(z) — k=35 соседей<br/>в обучающей выборке (clean)"]
    KNN --> RD["Слой 3: reach-dist_k(z, o)<br/>= max(d_k(o), d(z, o))"]
    RD --> LRD["Слой 4: lrd_k(z)<br/>= 1 / mean reach-dist"]
    LRD --> LOF["Слой 5: LOF_k(z)<br/>= mean( lrd_k(oᵢ) / lrd_k(z) )"]
    LOF --> DEC{"LOF_k(z) ≷ порог<br/>(определяется<br/>contamination=0.05)"}
    DEC -- ниже --> CLEAN["pred = +1 → clean"]
    DEC -- выше --> SYN["pred = −1 → synthetic"]
```

## Граф вычислений для одного образца (novelty inference)

```mermaid
flowchart LR
    X["x ∈ ℝ¹³"] --> M["(x − μ) / σ → z"]
    M --> KQ["query kNN-индекса<br/>(построен на X_train)"]
    KQ --> NB["соседи o₁..o_k<br/>и расстояния d(z, oᵢ)"]
    NB --> RD["reach-dist_k(z, oᵢ)<br/>= max(d_k(oᵢ), d(z, oᵢ))"]
    RD --> LRDz["lrd_k(z)"]
    NB --> LRDo["lrd_k(oᵢ) — кэш<br/>с этапа fit()"]
    LRDo --> RATIO["lrd_k(oᵢ) / lrd_k(z)"]
    LRDz --> RATIO
    RATIO --> AVG["mean по i"]
    AVG --> LOFv["LOF_k(z)"]
    LOFv --> DF["decision_function(z)<br/>= −LOF_k(z) + offset_"]
    DF --> SGN["sign"]
    SGN --> Y["predict ∈ {−1, +1}"]
    DF --> SCORE["−decision_function → anomaly_score<br/>(для ROC/PR)"]
```

В режиме `novelty=True` индекс `kNN` и значения `lrd_k(oᵢ)` обучающих точек
фиксируются на этапе `fit(X_train)`, а для нового `x` пересчитывается только
`lrd_k(x)` и итоговый `LOF_k(x)`. В `compare_classic_models.py` бинарная метка
`synthetic` получается из `predict == -1`, а непрерывный score — из
`-decision_function(x)`.
