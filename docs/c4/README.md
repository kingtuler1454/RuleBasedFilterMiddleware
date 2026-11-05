# C4-диаграммы Python-модулей

Полный набор C4-диаграмм (Context → Container → Component → Code) для
Python-инструментов из каталога `scripts/`. Исходники на C# (`.cs`) намеренно
не рассматриваются.

Все диаграммы написаны в Mermaid (`C4Context`, `C4Container`, `C4Component`,
`flowchart`, `sequenceDiagram`) и рендерятся прямо в GitHub.

## Содержание

| Уровень | Файл | Что показывает |
|---|---|---|
| 1. Context  | [`01-context.md`](01-context.md)     | Python-подсистема как «чёрный ящик» и её внешние акторы/системы |
| 2. Container| [`02-container.md`](02-container.md) | Каждый `.py`-модуль = отдельный исполняемый контейнер |
| 3. Component| [`03-component-intrusion.md`](03-component-intrusion.md)                           | `scripts/traffic/intrusion.py` |
|             | [`03-component-export-opensearch-since.md`](03-component-export-opensearch-since.md) | `scripts/data/export_opensearch_since.py` |
|             | [`03-component-merge-raw-jsons.md`](03-component-merge-raw-jsons.md)                 | `scripts/data/merge_raw_jsons.py` |
|             | [`03-component-build-windows.md`](03-component-build-windows.md)                     | `scripts/data/build_windows.py` |
|             | [`03-component-train-model.md`](03-component-train-model.md)                         | `scripts/ml/train_model.py` |
|             | [`03-component-experiments-iforest.md`](03-component-experiments-iforest.md)         | `scripts/ml/experiments_iforest.py` |
|             | [`03-component-compare-classic-models.md`](03-component-compare-classic-models.md)   | `scripts/ml/compare_classic_models.py` |
|             | [`03-component-ml-service.md`](03-component-ml-service.md)                           | `scripts/ml/ml_service.py` |
| 4. Code     | [`04-code.md`](04-code.md)           | Поток данных пайплайна и sequence для `POST /predict` |

## Краткая сводка по модулям

| Модуль | Роль | Внешние зависимости |
|---|---|---|
| `scripts/traffic/intrusion.py`            | Генератор трафика (5 режимов)            | Tile API (HTTP) |
| `scripts/data/export_opensearch_since.py` | Выгрузка хитов из OpenSearch             | OpenSearch, FS |
| `scripts/data/merge_raw_jsons.py`         | Слияние raw JSON и проставление меток    | FS |
| `scripts/data/build_windows.py`           | Сборка оконных признаков (W=30, S=5)     | FS |
| `scripts/ml/train_model.py`               | Обучение IsolationForest                 | FS |
| `scripts/ml/experiments_iforest.py`       | Гипер-перебор IF + ROC/PR/score-hist     | FS, matplotlib |
| `scripts/ml/compare_classic_models.py`    | Сравнение IF / OCSVM / LOF               | FS, matplotlib |
| `scripts/ml/ml_service.py`                | FastAPI-сервис онлайн-инференса          | OpenSearch, FS, Tile API |
