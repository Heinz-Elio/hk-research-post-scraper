# HK Research Post Scraper

Lightweight BeautifulSoup-based scraper for **Research Assistant** and related research posts from major Hong Kong universities.

## Features

- Separate scrapers per university (`scrapers.py`)
- Clean main orchestration (`scraper.py`)
- Saves to `research_posts.json` (active)
- Automatically moves expired posts to `outdated_posts.json`
- Optional local embeddings (`all-MiniLM-L6-v2`) for semantic search
- Extracts: `id`, `title`, `close_date`, `content`, `url`, `source`, `scraped_at`

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

# Optional for embeddings
pip install sentence-transformers numpy
```

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
  "content": ".... full job description ....",
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
