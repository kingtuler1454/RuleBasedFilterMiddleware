# Pipeline признаков и онлайн-инференс

В этом документе показан **полный путь** от сырого HTTP-запроса до ML-предсказания:
как формируются признаки в офлайн-обучении (`experiments_iforest.py`) и как они
строятся «на лету» в сервисе инференса `scripts/ml/ml_service.py`.

## Офлайн: построение оконных признаков

Источник: `scripts/ml/experiments_iforest.py`, функция `build_windows`.

```mermaid
flowchart TB
    RAW[("requests_merged_labeled.csv<br/>userIp, sessionId, requestTime,<br/>x, y, z, sourceLabel")]
    RAW --> CLEAN["pd.to_datetime / to_numeric<br/>dropna по ключевым полям"]
    CLEAN --> GID["groupId =<br/>userIp + '|' + sessionId<br/>(или '|no-session')"]
    GID --> SORT["sort by requestTime<br/>в каждой группе"]
    SORT --> WIN["скользящее окно<br/>window ∈ {20, 30, 50}, step = 5"]
    WIN --> AGG_IN["агрегация на окне"]

    subgraph AGG["Агрегация одного окна (N запросов)"]
        direction TB
        c1[req_count = N]
        c2["x_std, y_std, z_std = std(x/y/z)"]
        c3["x_unique, y_unique, z_unique = #unique"]
        c4["dx = diff(x), dy = diff(y)"]
        c5["mean_abs_dx, mean_abs_dy"]
        c6["t = requestTime (sec)"]
        c7["dt = diff(t), clip ≤ 0 → 1e-6"]
        c8["mean_dt, std_dt, min_dt, max_dt"]
    end

    AGG_IN --> AGG
    AGG --> VEC["Вектор признаков x ∈ ℝ¹³<br/>+ sourceLabel (мода окна)"]
    VEC --> SPLIT{"sourceLabel"}
    SPLIT -- "clean" --> XTR[X_train]
    SPLIT -- "all" --> XTE[X_test]
    XTR --> FIT["model.fit(X_train)"]
    XTE --> PRED["model.predict(X_test)<br/>model.score_samples(X_test)"]
```

## Онлайн-инференс: `ml_service.py`

FastAPI-сервис принимает `userIp` пользователя, достаёт его последние запросы
из OpenSearch и считает сокращённый набор признаков прямо в `extract_features_from_requests`.

```mermaid
flowchart LR
    REQ[/"POST /predict<br/>{ userIp, parameters }"/]
    REQ --> OS["OpenSearch.search<br/>index=requests<br/>match userIp, sort desc, size=50"]
    OS --> HITS["last 50 requests<br/>каждого пользователя"]
    HITS --> CHK{"len &lt; 2 ?"}
    CHK -- да --> DEFAULT["PredictionResponse<br/>is_legitimate=True<br/>confidence=0.5"]
    CHK -- нет --> EX_IN[extract_features_from_requests]

    subgraph EX["extract_features_from_requests"]
        direction TB
        e1["x_coords, y_coords, z_coords<br/>из parameters.x/y/z"]
        e2["std(x), std(y),<br/>#unique(x), #unique(y)"]
        e3["time_diffs = Δ requestTime<br/>(в секундах)"]
        e4["mean(time_diffs),<br/>std(time_diffs)"]
        e5["features ∈ ℝ⁶<br/>reshape(1, -1)"]
        e1 --> e2
        e1 --> e3
        e3 --> e4
        e2 --> e5
        e4 --> e5
    end

    EX_IN --> EX
    EX --> SZ{"features.size == 0 ?"}
    SZ -- да --> DEFAULT
    SZ -- нет --> M["model = joblib.load(<br/>'intrusion_detection_model.pkl')<br/>model.predict(features)<br/>model.predict_proba(features)"]
    M --> RESP["PredictionResponse<br/>is_legitimate = (pred == 1)<br/>confidence = max(proba)"]
    DEFAULT --> OUT[/JSON ответ/]
    RESP --> OUT
```

> ⚠️ Признаки в `ml_service.py` (6 значений: `std(x)`, `std(y)`, `#unique(x)`,
> `#unique(y)`, `mean(dt)`, `std(dt)`) — это **подмножество** офлайн-набора из
> 13 признаков. Для совместимости с моделями из `experiments_iforest.py` /
> `compare_classic_models.py` потребовалось бы расширить онлайн-извлечение
> признаков до полного списка из [README.md](./README.md).

## Сводный граф «данные → модель → решение»

```mermaid
flowchart LR
    A["Сырые HTTP-запросы<br/>(x, y, z, requestTime, userIp, sessionId)"]
    A --> B["Группировка по<br/>userIp + sessionId"]
    B --> C["Скользящее окно<br/>+ агрегаты ℝ¹³"]
    C --> D{"Модель"}
    D --> D1["Isolation Forest<br/>ансамбль iTree → score"]
    D --> D2["One-Class SVM (RBF)<br/>Σ αᵢ K(x, xᵢ) − ρ"]
    D --> D3["LOF (k=35)<br/>locаl density ratio"]
    D1 --> E["anomaly_score, predict ∈ {−1, +1}"]
    D2 --> E
    D3 --> E
    E --> F{"predict == −1 ?"}
    F -- да --> SY[synthetic / bot]
    F -- нет --> CL[clean / human]
```
