# Cline's scrape.py
==================

A small command-line tool that searches DuckDuckGo for a query, visits the top results with Playwright, extracts the main readable text from each page (using readability-lxml + BeautifulSoup), truncates the result to a configured maximum number of words, and saves the results to a Markdown file.

## Features
- Perform a DuckDuckGo search and collect the top N result URLs
- Visit each result in a real browser (Playwright)
- Extract the article/main content using readability
- Clean HTML to plain text with BeautifulSoup
- Save results to an easy-to-read Markdown file

## Requirements
- Python 3.8+
- pip packages: playwright, readability-lxml, beautifulsoup4

## Quick install

    python3 -m pip install --upgrade pip
    python3 -m pip install playwright readability-lxml bs4
    python3 -m playwright install --with-deps

Note: The repository contains an example devcontainer configuration (.devcontainer/devcontainer.json) that installs system packages and the required Python packages automatically. See the "Devcontainer / Docker" section below.

## Usage

**Basic invocation (uses built-in default search query):**

    python3 scrape.py

**Specify a query and options:**

    xvfb-run -a python3 scrape.py "best console editor for linux" -n 5 -m 800 -o results.md
    
**Options**
- query (positional): Search query (defaults to "best console editor for linux")
- -n, --num-sites: Number of search results to scrape. Default: 3
- -m, --max-words: Maximum words to keep from each site. Default: 1000
- -o, --output: Path to output Markdown file. Default: output.md
- - --append: Append to existing file instead of overwriting
- - --verbatim: Enable printed progress output. By default the scraper is silent and only writes errors to stderr; pass --verbatim to see Searching/Opening/Saved messages.
- - --headless: Run the browser in headless mode (the script defaults to headed), **not recommended will be challenged by CAPTCHAs everywhere**

**Output format**

The output Markdown contains one section per URL. Each entry looks like:

    ## https://example.com/some-article

    <first N words of cleaned article text>

    ---

Where '---' separates entries.

## Devcontainer / Docker (example)

This repository includes a .devcontainer/devcontainer.json file intended for use with VS Code's Remote - Containers (Dev Containers) feature. The example devcontainer uses the official base image and runs a post-create command that installs python3, pip, xvfb, the Python dependencies and Playwright browsers.

**How to use the example devcontainer:**

- In VS Code: Install "Dev Containers" (or the Remote - Containers extension), then open the repository and choose "Reopen in Container". The postCreateCommand will run and install required packages.
- Using the devcontainers CLI (optional):

    devcontainer up --workspace-folder .

The .devcontainer/devcontainer.json provided in this repo contains:

```json
{
  "name": "Scraper",
  "image": "mcr.microsoft.com/devcontainers/base:jammy",
  "runArgs": ["--privileged","--cap-add=ALL"],
  "remoteUser": "root",
  "postCreateCommand": "apt-get update && apt-get install -y python3 python3-pip xvfb && pip3 install playwright readability-lxml bs4 && playwright install --with-deps"
}
```

## Notes
- The script defaults to running a headed browser so you can watch navigation. Pass --headless to run without UI. On headless Linux servers you may need Xvfb or a display.
- Playwright must install its browser binaries (see `python3 -m playwright install --with-deps`). The devcontainer post-create step runs this for you.
- The scraper uses short random delays (human-like) between page actions. Respect robots.txt and site terms of service — don't use this script to perform aggressive automated scraping of sites that disallow it.

## Troubleshooting
- If you see Playwright timeout errors, try running without --headless so you can observe the browser, or increase timeouts in the code.
- If extraction yields no readable content for a site, the script will skip it and continue. Make sure the target page contains an article/main content — some heavier client-side sites may require additional rendering.

## Development notes
- Relevant functions in scrape.py:
  - fetch_search_results(page, query, num_sites)
  - scrape_page(page, url, max_words)
  - extract_main_text(html)
  - write_markdown(output_path, results, append)
- Feel free to adjust human_delay(), default flags, or the extraction pipeline (e.g., tune readability options) to improve results.

## License
This project is released under the GNU General Public License version 3 (GPLv3).
See the LICENSE.txt file in the repository root for the full text and license
obligations. The source files include short copyright headers that point to the
LICENSE.txt.

## Third-party components
This project depends on third-party packages that are licensed under other
licenses (see NOTICE). Notably, Playwright and readability-lxml are used and
are distributed under the Apache License 2.0. The NOTICE file in the repository
contains attribution for Apache-2.0 components and should be included with any
redistribution as required by Apache-2.0.
