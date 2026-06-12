# C4 Level 2 — Container Diagram: C# Solution

Показывает контейнеры .NET-решения `YmlRulesFileParser.sln` и их взаимодействие
с внешними системами.

```mermaid
C4Container
    title C4 Level 2 — Containers: C#-решение RuleBasedFilterMiddleware

    Person(webClient, "Web Client", "Браузер / HTTP-клиент.<br/>Запрашивает тайловые изображения<br/>через client.html")

    System_Ext(mapTiler, "MapTiler API", "Внешний тайловый сервер.<br/>api.maptiler.com<br/>GET /maps/openstreetmap/256/{z}/{x}/{y}.png")
    System_Ext(mlService, "ML Service", "Python FastAPI, порт 8000.<br/>POST /predict — онлайн-инференс<br/>модели обнаружения аномалий")
    SystemDb_Ext(openSearch, "OpenSearch", "Хранилище истории запросов.<br/>Индекс 'requests'. HTTPS:9200")

    System_Boundary(solution, "YmlRulesFileParser.sln (.NET)") {

        Container_Boundary(tileApiBoundary, "TestTileApi") {
            Container(tileApi, "TestTileApi", "ASP.NET Core Web API, C#", "Прокси-сервер тайлов.<br/>Принимает GET /Tiles?z&x&y,<br/>проксирует запрос к MapTiler,<br/>защищён фильтрующим middleware.")
        }

        Container_Boundary(webAppBoundary, "TestWebApplication") {
            Container(webApp, "TestWebApplication", "ASP.NET Core Web API, C#", "Тестовое веб-приложение.<br/>Демонстрирует базовое<br/>правило-ориентированное<br/>фильтрование запросов.")
        }

        Container_Boundary(libBoundary, "RuleBasedFilterLibrary (NuGet)") {
            Container(middleware, "Middleware", ".NET, ASP.NET Core", "RuleBasedRequestFilterMiddleware.<br/>Перехватывает каждый HTTP-запрос,<br/>возвращает 403 при нарушении правил.")
            Container(core, "Core", ".NET, C#", "Доменные модели и сервисы:<br/>правила (Rules), политики доступа<br/>(AccessPolicies), анализ<br/>последовательностей запросов<br/>(SequenceAnalysis), фабрики.")
            Container(infrastructure, "Infrastructure", ".NET, C#", "Инфраструктурные сервисы:<br/>OpensearchRequestStorage — чтение/<br/>запись истории запросов,<br/>RulesLoader — парсинг rulesConf.yml.")
            Container(extensions, "Extensions", ".NET, C#", "DI-расширения: регистрация<br/>сервисов, middleware и<br/>настроек фильтра.")
        }
    }

    Rel(webClient, tileApi, "GET /Tiles?z&x&y", "HTTP/HTTPS")
    Rel(webClient, webApp, "HTTP-запросы для тестирования", "HTTP/HTTPS")

    Rel(tileApi, middleware, "использует (in-process)")
    Rel(webApp, middleware, "использует (in-process)")
    Rel(middleware, core, "вызывает IRequestValidationService")
    Rel(core, infrastructure, "читает историю запросов<br/>через IRequestStorage")
    Rel(core, extensions, "конфигурируется через DI")

    Rel(tileApi, mapTiler, "GET /256/{z}/{x}/{y}.png", "HTTPS")
    Rel(infrastructure, openSearch, "GetRequestsOfUser / AddAsync", "HTTPS, opensearch-client")
    Rel(tileApi, mlService, "POST /predict<br/>(MLSequenceAnalyzer)", "HTTP/JSON")

    Rel(infrastructure, core, "поставляет модели запросов")
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
