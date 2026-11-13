# HK Research Post Scraper

Collector for research posts (Research Assistant, Postdoc, research associate/officer/analyst, and similar grades) scraped **directly from university career pages** — not job boards. Appointments are kept in any discipline. Clerical, finance, HR, and admissions grades are left out.

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
| Research grades | Keeps research appointments in any discipline; drops clerks, executive officers, admissions, HR, and finance |
| Min degree | Lowest stated requirement; UI **I hold** hides posts above your level |
| Domain tags | Controlled tags (AI/ML, CS, health, …). SPSS, "research materials", and bioinformatics are not tagged as computer science |
| Summaries | Short extractive lines (dept, role, requirements, terms, date, contact). A local model is optional and off |
| Dates | Hard deadlines expire; a review-start or "open until filled" post stays active while it is listed |
| Browse filters | Optional: work type, degree, contract length, Hong Kong vs Guangzhou, and closing within 30 days. All default to off |
| Storage | `research_posts.json` (active), `outdated_posts.json` |
| Embeddings | Quantized vectors in `docs/embeddings.json` (not in the listing JSON) |
| Semantic search | Pages: MiniLM in the browser; CLI: `python main.py --search "..."` |
| Request update | Button sends a note through FormSubmit. No GitHub account |

## Supported sources

| Key | University | Notes |
|-----|------------|--------|
| HKU | University of Hong Kong | Table + department |
| PolyU | PolyU | Research table: dept + project |
| CityU | CityU | Research positions + dept |
| CUHK | CUHK | Taleo REST; department/unit |
| HKUST | HKUST CWB | teaching-support listing + division |
| HKUST-GZ | HKUST Guangzhou | Career JSON API; Chinese titles included |
| HKBU | HKBU | Oracle Recruiting Cloud REST |
| Lingnan | Lingnan | CSOD job-search API (research-support category) |
| EdUHK | EdUHK | research-support-posts category |
| HKMU | HKMU | Taleo REST; research titles in any discipline |

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

### Optional: Playwright (bot checks)

Plain HTTP cannot pass AWS WAF (HKU) or Incapsula (CityU detail pages). When that happens, `fetch()` opens the same URL in Chrome, Edge, or Chromium, waits until the bot check clears or the job rows appear, then copies the cookies back so later pages can stay on HTTP.

CUHK, HKMU, HKBU, Lingnan and HKUST(GZ) use their public JSON APIs and do not need a browser. A post is kept when the title is a research appointment (research assistant/associate/officer/fellow/analyst, postdoc, research engineer or scientist, project assistant/associate outside an admin office), including Chinese titles such as `研究助理` and `博士后`. Technical and engineer titles still need a discipline or a research word.

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

The Pages UI embeds a query with `Xenova/all-MiniLM-L6-v2` only after the first search. Until that model loads, search is keyword-only. The default browse order lists future deadlines and future review-start dates first, then open-ended posts by newest scrape.

## Config (`main.py`)

```python
USE_LOCAL_SUMMARIZER = False   # extractive summary is the default; the model is optional
USE_EMBEDDINGS = False
SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
```

## Usage

```bash
python main.py                      # all registered sources
python main.py --sources HKU,PolyU
python main.py --force              # ignore listing hashes (--ignore-hashes)
python main.py --dry-run            # scrape into a temp directory; repo JSON is not touched
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
  "summary": "- Dept: Department of Computer Science\n- Role focus: ...\n- Requirements: ...\n- Contact: name@hku.hk",
  "date_type": "deadline",
  "possibly_stale": false,
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

- Research appointments are kept across disciplines. Admin roles still drop. A clerk or clerical grade in the title or in the advertisement ("at the rank of Clerk", "Clerk grade", 文員/文员/文書) drops the post even when the functional title is a project or research grade. HKMU titles such as "Research Assistant I/II (N&HS)" match on the title.
- A listing hash is stored only after the JSON save, and never for an empty listing. `--force` re-fetches anyway. PolyU's screening date is `date_type: review_start` and does not move a post to outdated while the post is still listed.
- HKUST(GZ) keeps an empty closing date when the API's offline date is the open-ended sentinel `3000-01-02`. HKBU and Lingnan do the same when the source publishes no deadline.
- Be polite: delay between detail requests is already set. Lingnan's careers host asks for a 10-second crawl delay; the scraper hits that host once per run.
- Personal research-job monitoring only; respect each university’s terms.
