# HK Research Post Scraper

Lightweight scraper for **Engineering & Science** research posts (Research Assistant, Postdoc, etc.) from major Hong Kong universities.

- BeautifulSoup for static sites
- **Playwright** for JS-heavy portals (HKBU, Lingnan)
- Short **summary** (optional local model) instead of full job text
- Classification: `work_type`, `degree_level`, `department`
- Active / outdated JSON + optional embeddings for semantic search

## Web front (GitHub Pages)

The simple filter/sort UI lives under **`docs/`** (required folder for Pages):

- Source: [docs/index.html](docs/index.html)
- Enable Pages: **Settings → Pages → Deploy from branch → `/docs`**
- Data URL in the page should point at raw JSON, e.g.  
  `https://raw.githubusercontent.com/Heinz-Elio/hk-research-post-scraper/main/research_posts.json`

After Pages is on, the site is typically:

`https://heinz-elio.github.io/hk-research-post-scraper/`

(Repo is private → Pages may need a Pro plan or public repo depending on your account.)

## Features

| Feature | Detail |
|--------|--------|
| STEM focus | Keeps Engineering / Science related research posts only |
| Filter fields | Uses **title + department + project** (not title alone) |
| Summaries | Optional small local model, else rule-based truncate |
| Classification | `work_type`, `degree_level`, `department` |
| Storage | `research_posts.json` (active), `outdated_posts.json` |
| Embeddings | Optional `all-MiniLM-L6-v2` for semantic search |
| Request update | Front has a button that opens a GitHub Issue |

## Supported sources

| Key | University | Notes |
|-----|------------|--------|
| HKU | University of Hong Kong | Table + department |
| PolyU | PolyU | Research table: dept + project |
| CityU | CityU | Research positions + dept |
| CUHK | CUHK | Taleo; department/unit |
| HKUST | HKUST CWB | teaching-support listing + division |
| HKUST-GZ | HKUST Guangzhou | Best-effort |
| HKBU | HKBU | **Playwright** (Oracle Cloud) |
| Lingnan | Lingnan | **Playwright** (CSOD) |
| EdUHK | EdUHK | research-support-posts category |
| HKMU | HKMU | Taleo (limited) |

## Install

```bash
git clone https://github.com/Heinz-Elio/hk-research-post-scraper.git
cd hk-research-post-scraper
pip install -r requirements.txt
```

### Optional: Playwright (HKBU + Lingnan)

```bash
pip install playwright
playwright install chromium
```

### Optional: Local summarizer

```bash
pip install transformers accelerate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # if no GPU
```

Default model: `Qwen/Qwen2.5-1.5B-Instruct` (change in `main.py`).

### Optional: Embeddings

```bash
pip install sentence-transformers numpy
```

## Config (`main.py`)

```python
USE_LOCAL_SUMMARIZER = True
USE_EMBEDDINGS = True
SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
```

Verbose transformers logs are suppressed. Device (cuda/cpu) is logged at startup.

## Usage

```bash
python main.py
```

```python
from main import run, semantic_search

run(sources=["HKU", "PolyU", "CityU", "HKUST"])
run()  # all sources

results = semantic_search("machine learning research assistant", top_k=5)
```

## Output shape

```json
{
  "id": "HKU_537585",
  "title": "Research Assistant ...",
  "close_date": "2026-12-12",
  "summary": "Short summary of role and requirements...",
  "work_type": "Full-time",
  "degree_level": "Master",
  "department": "Department of Computer Science",
  "url": "https://...",
  "source": "HKU",
  "scraped_at": "2026-10-10T18:30:00"
}
```

## Notes

- STEM filter uses department/project where the listing provides them; generic titles alone are dropped if no STEM signal.
- HKBU / Lingnan need Playwright; without it those scrapers skip cleanly.
- Be polite: delay between detail requests is already set.
- Personal research-job monitoring only; respect each university’s terms.
