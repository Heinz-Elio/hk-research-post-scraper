# HK Research Post Scraper

Lightweight BeautifulSoup-based scraper for **Research Assistant** and related research posts from major Hong Kong universities.

## Features

- Separate scrapers per university (`scrapers.py`)
- Clean main orchestration (`scraper.py`)
- Saves to `research_posts.json` (active)
- Automatically moves expired posts to `outdated_posts.json`
- **Optional local model summarization** (small instruct model) — stores a short `summary` instead of full content
- Optional local embeddings (`all-MiniLM-L6-v2`) for semantic search
- Extracts: `id`, `title`, `close_date`, `summary`, `url`, `source`, `scraped_at`

## Supported Sources

| Key        | University                      | Notes                          |
|------------|---------------------------------|--------------------------------|
| HKU        | University of Hong Kong         | Best quality (`class=job-link`)|
| PolyU      | The Hong Kong Polytechnic Univ. | Research / Project posts       |
| CityU      | City University of Hong Kong    | Research Positions page        |
| CUHK       | The Chinese University of HK    | Taleo (limited without JS)     |
| HKUST      | HKUST Clear Water Bay           | Career portal                  |
| HKUST-GZ   | HKUST Guangzhou                 |                                |
| HKBU       | Hong Kong Baptist University    |                                |
| Lingnan    | Lingnan University              |                                |
| EdUHK      | The Education University of HK  |                                |
| HKMU       | Hong Kong Metropolitan Univ.    | Taleo                          |

## Install

```bash
git clone https://github.com/Heinz-Elio/hk-research-post-scraper.git
cd hk-research-post-scraper
pip install -r requirements.txt
```

### Optional: Local Summarizer (recommended)

```bash
pip install transformers accelerate
# CPU-only torch (recommended if no GPU):
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Default model: `Qwen/Qwen2.5-1.5B-Instruct`  
You can change it at the top of `scraper.py`.

### Optional: Embeddings

```bash
pip install sentence-transformers numpy
```

## Config Switches (`scraper.py`)

```python
USE_LOCAL_SUMMARIZER = True          # set False → pure rule-based summary
USE_EMBEDDINGS = True

SUMMARIZER_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
# Other good small options:
# "meta-llama/Llama-3.2-1B-Instruct"
# "microsoft/Phi-3.5-mini-instruct"
```

- If the local model is not available / fails to load, it **automatically falls back** to a clean rule-based summary (first ~520 characters, cut at sentence boundary).
- Full job text is **never stored** — only the short `summary` is kept.

## Usage

```bash
# Scrape all sources
python scraper.py
```

Or from Python:

```python
from scraper import run, semantic_search

run(sources=["HKU", "PolyU", "CityU"])   # selected sources
run()                                    # all

# Semantic search (after embeddings generated)
results = semantic_search("machine learning computer vision research assistant", top_k=5)
for r in results:
    print(r)
```

## Output Format (example)

```json
{
  "id": "HKU_537585",
  "title": "Full-time/Part-time Research Assistant I/II (several posts)",
  "close_date": "2026-12-12",
  "summary": "The appointee will support a large-scale multidisciplinary youth mental health project... Requires a Bachelor's degree in psychology or related field...",
  "url": "https://jobs.hku.hk/en/job/537585/...",
  "source": "HKU",
  "scraped_at": "2026-10-10T18:30:00",
  "embedding": [0.012, -0.034, ...]   // only if enabled
}
```

## Notes

- Some sites (especially Taleo-based CUHK / HKMU) are JavaScript-heavy. The current scrapers get the initial HTML listing. For production-grade completeness consider adding Playwright later.
- Be polite: the scrapers already include a short delay between detail-page requests.
- Closing dates are parsed when available; many list pages do not show them → `null`.
- The tool is intended for personal research-job monitoring only. Respect each university’s terms of use.
