# HK Research Post Scraper

Collector for **Engineering & Science** research posts (Research Assistant, Postdoc, etc.) scraped **directly from university career pages** — not job boards.

- Plugin scrapers under `sources/` (copy `_template.py` to add a school or org)
- **Minimum academic requirement** (`min_degree` / `degree_rank`) and **domain tags**
- Short **summary** (optional local model) instead of full job text
- Active / outdated JSON + quantized embeddings for semantic search
- GitHub Pages UI: I-hold filter, domain chips, client-side MiniLM ranking

## Web front (GitHub Pages)

The filter/sort UI lives under **`docs/`**:

- Source: [docs/index.html](docs/index.html)
- Enable Pages: **Settings → Pages → Deploy from branch → `/docs`**
- Data: `docs/research_posts.json` plus `docs/embeddings.json` (optional, for semantic search)

After Pages is on, the site is typically:

`https://heinz-elio.github.io/hk-research-post-scraper/`

(Repo is private → Pages may need a Pro plan or public repo depending on your account.)

## Features

| Feature | Detail |
|--------|--------|
| School pages | Direct scrape of each university career site |
| STEM focus | Keeps Engineering / Science related research posts only |
| Min degree | Lowest stated requirement; UI **I hold** hides posts above your level |
| Domain tags | Controlled tags (AI/ML, CS, electronics, …), searchable and clickable |
| Summaries | Optional small local model, else rule-based truncate |
| Storage | `research_posts.json` (active), `outdated_posts.json` |
| Embeddings | Quantized vectors in `docs/embeddings.json` (not in the listing JSON) |
| Semantic search | Pages: MiniLM in the browser; CLI: `python main.py --search "..."` |
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

## Add another school or organisation

1. Copy [`sources/_template.py`](sources/_template.py) to `sources/<short_name>.py` (no leading underscore).
2. Set `KEY` and `NAME`, implement `scrape()` against **that org’s career page**.
3. Return dicts with `id`, `title`, `url`, `source`, `content` (optional `close_date`, `department`, `project`).
4. The module is auto-registered; run `python main.py --sources YourKey`.

Do not point scrapers at generic job aggregators.

## Install

```bash
git clone https://github.com/Heinz-Elio/hk-research-post-scraper.git
cd hk-research-post-scraper
pip install -r requirements.txt
```

### Optional: Playwright (bot checks and JS listings)

Plain HTTP cannot pass AWS WAF (HKU) or Incapsula (CityU detail pages), and Taleo (CUHK, HKMU) draws the job table only after JavaScript runs. When that happens, `fetch()` opens the same URL in Chrome, Edge, or Chromium, waits until the bot check clears or the job rows appear, then copies the cookies back so later pages can stay on HTTP.

```bash
pip install playwright
playwright install chromium
```

If Chrome or Edge is already installed, the scrapers use that and the Chromium download is optional.

### Optional: Local summarizer

```bash
pip install transformers accelerate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # if no GPU
```

Default model: `Qwen/Qwen2.5-1.5B-Instruct` (change in `main.py`).

### Optional: Embeddings (CLI encode + new vectors)

```bash
pip install sentence-transformers numpy
```

Set `USE_EMBEDDINGS = True` in `main.py` before a scrape that should write new vectors. Existing float embeddings are migrated into `docs/embeddings.json` with `--migrate-only` (no model required).

The Pages UI loads `Xenova/all-MiniLM-L6-v2` in the browser to embed the query.

## Config (`main.py`)

```python
USE_LOCAL_SUMMARIZER = False
USE_EMBEDDINGS = False
SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
```

## Usage

```bash
python main.py                      # all registered sources
python main.py --sources HKU,PolyU
python main.py --migrate-only       # re-tag stored posts; split embeddings
python main.py --search "vision transformer medical imaging"
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
  "min_degree": "master",
  "degree_rank": 2,
  "degree_level": "Master",
  "domains": ["ai-ml", "computer-science"],
  "department": "Department of Computer Science",
  "url": "https://...",
  "source": "HKU",
  "scraped_at": "2026-10-10T18:30:00"
}
```

`degree_rank`: unspecified=0, bachelor=1, master=2, doctor=3. **I hold** Master shows posts with rank ≤ 2 (or unspecified).

## Notes

- STEM filter uses department/project where the listing provides them; generic titles alone are dropped if no STEM signal.
- HKBU / Lingnan need Playwright; without it those scrapers skip cleanly.
- Be polite: delay between detail requests is already set.
- Personal research-job monitoring only; respect each university’s terms.
