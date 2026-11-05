# Isolation Forest

**Файлы:** `scripts/ml/train_model.py`, `scripts/ml/experiments_iforest.py`,
сравнение в `scripts/ml/compare_classic_models.py`.

## Конфигурация

| Параметр | Значение |
|---|---|
| `n_estimators` | 300 (`train_model.py`) / 500 (эксперименты, `compare_classic_models.py`) |
| `contamination` | 0.10 / перебор {0.05, 0.08, 0.10, 0.15} / 0.05 |
| `random_state` | 42 |
| Обучающая выборка | только `sourceLabel == "clean"` |
| Размерность входа | 13 признаков (см. [README.md](./README.md)) |

## Диаграмма «слоёв» (логических блоков)

Isolation Forest — это **ансамбль рандомизированных деревьев** (`iTree`).
В роли «слоёв» выступают этапы pipeline-а: входные признаки → ансамбль из `T`
независимых iTree → агрегация глубин в anomaly score → решающий порог.

```mermaid
flowchart TB
    X["Вход: x ∈ ℝ¹³<br/>(req_count, x/y/z_std, ...)"]
    subgraph ENS["Ансамбль iTree (T = n_estimators)"]
        direction LR
        T1[iTree 1]
        T2[iTree 2]
        TT[ ... ]
        TN[iTree T]
    end
    X --> T1
    X --> T2
    X --> TT
    X --> TN
    T1 --> H1["h₁(x) — глубина листа"]
    T2 --> H2["h₂(x)"]
    TN --> HN["h_T(x)"]
    H1 & H2 & HN --> AVG["E[h(x)] = (1/T) · Σ hᵢ(x)"]
    AVG --> SCORE["s(x, n) = 2^(−E[h(x)] / c(n))<br/>c(n) — средняя длина пути в BST"]
    SCORE --> DEC{"s(x) ≥ порог<br/>(контролируется<br/>contamination)?"}
    DEC -- да --> AN["pred = −1<br/>predLabel = synthetic"]
    DEC -- нет --> NO["pred = +1<br/>predLabel = clean"]
```

## Структура одного iTree

Каждое дерево строится рекурсивно на бутстрэп-подвыборке: на каждом узле
выбирается **случайный признак** `f` и **случайный порог** `p ∈ [min(f), max(f)]`,
точки делятся по условию `x[f] < p`. Деревья растут до изоляции точки или
до предельной глубины `ceil(log2(ψ))`, где `ψ` — размер подвыборки.

```mermaid
flowchart TB
    R["Узел<br/>выбрать случайный признак f<br/>и порог p ∈ [min, max]"]
    R -- "x[f] &lt; p" --> L["Левая ветка<br/>подвыборка S_L"]
    R -- "x[f] ≥ p" --> RR["Правая ветка<br/>подвыборка S_R"]
    L --> L1["рекурсия...<br/>до |S| = 1<br/>или depth = ⌈log₂ ψ⌉"]
    RR --> R1["рекурсия...<br/>до |S| = 1<br/>или depth = ⌈log₂ ψ⌉"]
    L1 --> Leaf1["Лист → длина пути h(x)"]
    R1 --> Leaf2["Лист → длина пути h(x)"]
```

## Граф вычислений для одного образца

Поток операций для конкретного входа `x` при инференсе
(`model.predict(x)` / `model.score_samples(x)`):

```mermaid
flowchart LR
    X["x ∈ ℝ¹³"] --> B1[iTree 1: traverse]
    X --> B2[iTree 2: traverse]
    X --> BT[ ... ]
    X --> BN[iTree T: traverse]
    B1 --> P1["h₁(x)"]
    B2 --> P2["h₂(x)"]
    BN --> PN["h_T(x)"]
    P1 & P2 & PN --> M["mean: E[h(x)]"]
    M --> N["normalize: E[h(x)] / c(n)"]
    N --> EXP["pow: 2^(−·)"]
    EXP --> S["anomaly_score s(x)"]
    S --> SHIFT["decision_function =<br/>s(x) − offset_<br/>(offset из contamination)"]
    SHIFT --> SGN["sign(·)"]
    SGN --> Y["predict ∈ {−1, +1}"]
```

Реализация в `experiments_iforest.py` использует `-model.score_samples(X)`
как непрерывный «anomaly score» для построения ROC/PR-кривых, а
`model.predict(X) == -1` интерпретируется как метка `synthetic`.
