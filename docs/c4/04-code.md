# C4 Level 4 — Code

C4 уровень 4 обычно изображают UML-диаграммой класса/последовательности.
Ниже — две диаграммы для двух самых нетривиальных мест системы:
поток данных пайплайна и онлайн-инференс `POST /predict`.

## 4.1 Поток данных пайплайна (offline)

```mermaid
flowchart LR
    OS[(OpenSearch<br/>index 'requests')]
    A[export_opensearch_since.py]
    R1[/requests_since.json<br/>requests_since.csv/]
    R2[/requests_raw.json + requests_raw2.json<br/>с метками clean/synthetic/]
    M[merge_raw_jsons.py]
    R3[/requests_merged_labeled.csv/]
    W[build_windows.py]
    R4[/windows_features.csv/]
    T[train_model.py]
    R5[/intrusion_detection_model.pkl<br/>iforest_scored.csv/]
    E[experiments_iforest.py]
    R6[/experiments_iforest.csv<br/>plots/*.png<br/>meta.json/]
    C[compare_classic_models.py]
    R7[/model_compare.csv<br/>plots_models/*.png/]
    S[ml_service.py<br/>FastAPI :8000]

    OS --> A --> R1
    R2 --> M --> R3
    R3 --> W --> R4
    R3 --> E --> R6
    R4 --> T --> R5
    R4 --> C --> R7
    R5 --> S
    OS --> S
```

## 4.2 Sequence — онлайн-инференс (`POST /predict`)

```mermaid
sequenceDiagram
    autonumber
    participant API as Tile API (.NET)
    participant SVC as ml_service.py (FastAPI)
    participant PYD as Pydantic
    participant OS as OpenSearch
    participant FE as extract_features_from_requests
    participant M as IsolationDetectionModel (.pkl)

    API->>SVC: POST /predict {userIp, parameters[]}
    SVC->>PYD: validate PredictionRequest
    PYD-->>SVC: ok
    SVC->>OS: search(index='requests',<br/>match userIp, sort desc, size=50)
    OS-->>SVC: hits[_source]
    alt hits пуст
        SVC-->>API: 200 {is_legitimate=true, confidence=0.5}
    else hits есть
        SVC->>FE: features([_source...])
        FE-->>SVC: ndarray(1, n) | empty
        alt features пуст
            SVC-->>API: 200 {is_legitimate=true, confidence=0.5}
        else
            SVC->>M: predict(features), predict_proba(features)
            M-->>SVC: pred, proba
            SVC-->>API: 200 {is_legitimate=(pred==1),<br/>confidence=max(proba)}
        end
    end
    note over SVC: при любой ошибке -> HTTP 500<br/>HTTPException(detail=str(e))
```
