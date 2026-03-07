# AutoScout24 Luxembourg ETL Scraper

Scraped täglich Fahrzeuginserate von AutoScout24.lu und speichert sie in DuckDB (Bronze + Silver Layer). Preisänderungen werden automatisch erkannt.

## Stack

| Tool | Zweck |
|------|-------|
| **Prefect 3.x** | Orchestrierung (Flows, Tasks, Scheduling) |
| **httpx** | Async HTTP-Requests |
| **selectolax** | HTML-Parsing via CSS-Selektoren |
| **DuckDB** | Lokale analytische Datenbank |
| **Pydantic v2** | Datenvalidierung & Modelle |
| **Docker + Traefik** | Deployment auf VPS |

## Projektstruktur

```
src/
├── models.py       # Pydantic-Modelle: Listing, PriceChange
├── extractors.py   # httpx + selectolax Scraping-Logik
├── database.py     # DuckDB read/write (Bronze + Silver Layer)
├── flows.py        # Prefect Flows & Tasks
└── main.py         # CLI Entry Point

Dockerfile.worker   # Worker-Image für VPS
prefect.yaml        # Deployment-Konfiguration (git_clone + pip_install)
requirements.txt    # Python-Dependencies für Prefect Pull-Step
```

## Infrastruktur (VPS)

Prefect läuft auf dem VPS unter **https://prefect.vps.riespatrick.de**

### Docker Compose Services

- **postgres** — Prefect-Metadaten-Datenbank
- **prefect-server** — Prefect UI + API (via Traefik mit TLS)
- **prefect-worker** — Process Worker, pullt Code von GitHub bei jedem Run

### Code-Deployment Flow

```
git push origin main
         ↓
prefect deploy --all  (registriert Deployments beim VPS-Server)
         ↓
Flow-Run getriggert → Worker klont Repo von GitHub → pip install → Flow startet
```

## Lokale Entwicklung

```bash
# Venv aktivieren
.venv\Scripts\activate

# CLI nutzen
python -m src.main scrape --make audi --model a4

# Prefect lokal
prefect server start
prefect deploy --all
```

## Deployment auf VPS

```powershell
# 1. Code pushen
git push origin main

# 2. Deployments registrieren
$env:PREFECT_API_URL = "https://prefect.vps.riespatrick.de/api"
prefect deploy --all

# 3. Manuellen Run triggern
prefect deployment run 'scrape-flow/scrape-single'
```

## Scraping-Ziel

- **URL-Schema:** `https://www.autoscout24.lu/lst/{make}/{model}?sort=standard&desc=0&ustate=N,U&atype=C&cy=L`
- **Article-Selector:** `article.cldt-summary-full-item`
- **Pagination:** `&page=N`, stoppt bei leerer Seite
- **Daten:** `data-guid`, `data-price`, `data-mileage`, `data-fuel-type`, `data-first-registration`, `data-seller-type`

## Datenbank

```
data/autoscout.duckdb          (lokal)
/opt/prefect/scraper-data/     (VPS via Volume Mount)

Tabellen:
  raw_listings    — Bronze: append-only, eine Zeile pro Run
  listings        — Silver: aktueller Stand, upserted
  price_changes   — erkannte Preisänderungen
```

## Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `AUTOSCOUT_DB_PATH` | `data/autoscout.duckdb` | Pfad zur DuckDB-Datei |
| `PREFECT_API_URL` | `http://localhost:4200/api` | Prefect Server URL |
