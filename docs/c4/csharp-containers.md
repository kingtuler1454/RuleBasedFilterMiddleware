# C4 Level 2 — Container Diagram: C# Solution

Показывает контейнеры .NET-решения `YmlRulesFileParser.sln` и их взаимодействие
с внешними системами.

```mermaid
flowchart TD
    classDef person   fill:#08427b,color:#fff,stroke:#073b6f,rx:50
    classDef container fill:#1168bd,color:#fff,stroke:#0b4f9a
    classDef ext      fill:#6b6b6b,color:#fff,stroke:#555
    classDef db       fill:#6b6b6b,color:#fff,stroke:#555

    WebClient(["👤 Web Client\n─────────────\nБраузер / HTTP-клиент"]):::person

    subgraph Solution["⬜ YmlRulesFileParser.sln  ·  .NET"]
        direction TB

        subgraph Apps["Приложения"]
            direction LR
            TileApi["🟦 TestTileApi\n─────────────\nASP.NET Core Web API\nПрокси тайлового сервера"]:::container
            WebApp["🟦 TestWebApplication\n─────────────\nASP.NET Core Web API\nТестовое приложение"]:::container
        end

        subgraph Library["RuleBasedFilterLibrary  ·  NuGet"]
            direction LR
            MW["🟦 Middleware\n─────────────\nПерехват запросов\nHTTP 403 при нарушении"]:::container
            Core["🟦 Core\n─────────────\nДоменная логика:\nправила, политики,\nанализ последовательностей"]:::container
            Infra["🟦 Infrastructure\n─────────────\nOpenSearch-адаптер\nYAML-парсер правил"]:::container
            Ext["🟦 Extensions\n─────────────\nDI-регистрация\nсервисов и middleware"]:::container
        end
    end

    MapTiler["🗺 MapTiler API\n─────────────\nВнешний тайловый сервер\napi.maptiler.com"]:::ext
    MLSvc["🤖 ML Service\n─────────────\nPython FastAPI :8000\nПредсказание аномалий"]:::ext
    OpenSearch[("🗄 OpenSearch\n─────────────\nИндекс 'requests'\nИстория запросов")]:::db

    %% ── внешние входы ──
    WebClient -- "GET /Tiles?z&x&y" --> TileApi
    WebClient -- "HTTP-запросы" --> WebApp

    %% ── in-process зависимости ──
    TileApi --> MW
    WebApp  --> MW
    MW      --> Core
    Core    --> Infra
    Core    --> Ext

    %% ── внешние вызовы ──
    TileApi  -- "GET тайл\nHTTPS" --> MapTiler
    TileApi  -- "POST /predict\nHTTP/JSON" --> MLSvc
    Infra    -- "search / index\nHTTPS" --> OpenSearch
```

## Легенда контейнеров

| Контейнер | Тип | Назначение |
|---|---|---|
| **TestTileApi** | ASP.NET Core Web API | Прокси-сервер тайловых изображений с защитой от массового скачивания |
| **TestWebApplication** | ASP.NET Core Web API | Тестовое приложение для демонстрации базового фильтрования |
| **Middleware** | .NET-библиотека (in-process) | Перехватывает HTTP-запросы и применяет правила фильтрации |
| **Core** | .NET-библиотека (in-process) | Доменная логика: правила, политики, анализ последовательностей |
| **Infrastructure** | .NET-библиотека (in-process) | Адаптеры: хранение запросов в OpenSearch, загрузка правил из YAML |
| **Extensions** | .NET-библиотека (in-process) | Методы расширения для регистрации сервисов в DI-контейнере |
| **OpenSearch** | Внешняя БД | Хранит историю HTTP-запросов для анализа последовательностей |
| **MapTiler API** | Внешний сервис | Источник тайловых изображений карты |
| **ML Service** | Внешний сервис (Python) | FastAPI-сервис инференса модели IsolationForest для обнаружения аномалий |
