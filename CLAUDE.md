# AutoScout24 Luxembourg ETL Scraper

## Stack
- **Orchestrator:** Prefect 3.x (@flow, @task Decorators)
- **HTTP Client:** httpx (async)
- **HTML Parser:** selectolax (schnell, CSS-Selektoren)
- **Datenbank:** DuckDB (lokal, analytische Queries)
- **Modelle:** Pydantic v2 (Validierung, Serialisierung)
- **Python:** 3.12+

## Architektur
```
src/
├── models.py          # Pydantic-Modelle: Listing, PriceChange
├── extractors.py      # httpx + selectolax Scraping-Logik
├── database.py        # DuckDB read/write
├── flows.py           # Prefect Flows und Tasks
└── main.py            # CLI Entry Point
```

## Regeln
- Verwende `@task(retries=3)` für alle HTTP-Requests
- Verwende `@flow(log_prints=True)` für Haupt-Flows
- Preisänderungen per DuckDB-SQL erkennen, NICHT Python-Loops
- Alle Scraping-Funktionen async mit httpx.AsyncClient
- Pydantic-Modelle für ALLE Datenstrukturen
- Type Hints überall
- Kein pandas – verwende DuckDB SQL oder Polars
- Kein requests – verwende httpx
- Kein BeautifulSoup – verwende selectolax

## Scraping-Ziel
- URL: https://www.autoscout24.lu/lst/{make}/{model}?sort=standard&desc=0&ustate=N,U&atype=C&cy=L
- Article-Element: `article.cldt-summary-full-item`
- Daten aus data-* Attributen: data-guid, data-price, data-mileage, data-fuel-type, data-first-registration, data-seller-type
- Pagination: `&page=N`, stoppe bei leerer Seite

## MCP-Server verfügbar
- `prefect`: Flow-Runs, Deployments, Logs abfragen
- `duckdb`: SQL-Queries direkt auf die Datenbank