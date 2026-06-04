# One-Class SVM (RBF)

**Файл:** `scripts/ml/compare_classic_models.py`

В коде модель обёрнута в `sklearn.pipeline.Pipeline`:

```python
Pipeline([
    ("scaler", StandardScaler()),
    ("ocsvm", OneClassSVM(kernel="rbf", nu=0.05, gamma="scale")),
])
```

| Параметр | Значение |
|---|---|
| Препроцессинг | `StandardScaler` (центрирование + масштабирование) |
| Ядро | RBF: `K(x, xᵢ) = exp(−γ · ‖x − xᵢ‖²)` |
| `nu` | 0.05 (верхняя граница доли «выбросов» в обучении) |
| `gamma` | `"scale"` → `1 / (n_features · Var(X))` |
| Обучающая выборка | только `sourceLabel == "clean"` |

## Диаграмма «слоёв» pipeline-а

```mermaid
flowchart TB
    X["Вход: x ∈ ℝ¹³"]
    X --> SC["Слой 1: StandardScaler<br/>z = (x − μ) / σ"]
    SC --> KER["Слой 2: RBF-ядро<br/>φ(z) — неявное отображение<br/>в гильбертово пространство"]
    KER --> SV["Слой 3: опорные векторы (SVs)<br/>{ (αᵢ, zᵢ) : αᵢ &gt; 0 }"]
    SV --> DEC["Слой 4: decision function<br/>f(z) = Σ αᵢ · K(zᵢ, z) − ρ"]
    DEC --> SGN["Слой 5: знак<br/>sign(f(z))"]
    SGN --> OUT{"predict"}
    OUT -- "+1" --> CLEAN[clean]
    OUT -- "−1" --> SYN[synthetic / anomaly]
```

«Опорные векторы» формируются на этапе обучения как решение задачи
квадратичного программирования с ограничением `nu`: модель ищет гиперплоскость
в RBF-пространстве, отделяющую начало координат от данных с максимальным
зазором, и сохраняет ненулевые `αᵢ` вместе с соответствующими `zᵢ`.

## Граф вычислений для одного образца

```mermaid
flowchart LR
    X["x ∈ ℝ¹³"] --> M["x − μ"]
    M --> D["÷ σ → z"]
    D --> K1["K(z, z₁)<br/>= exp(−γ‖z − z₁‖²)"]
    D --> K2["K(z, z₂)"]
    D --> KK[ ... ]
    D --> KN["K(z, z_S)<br/>S = #SVs"]
    K1 --> W1["α₁ · K"]
    K2 --> W2["α₂ · K"]
    KN --> WN["α_S · K"]
    W1 & W2 & WN --> SUM["Σ αᵢ · K(z, zᵢ)"]
    SUM --> SUB["− ρ"]
    SUB --> F["decision_function f(z)"]
    F --> SGN["sign"]
    SGN --> Y["predict ∈ {−1, +1}"]
    F --> SCORE["−f(z) → anomaly_score<br/>(используется для ROC/PR)"]
```

В `compare_classic_models.py` функция `get_anomaly_score` берёт именно
`-decision_function(x)` как непрерывный показатель аномальности; `predict == -1`
переводится в бинарную метку `synthetic = 1`.
