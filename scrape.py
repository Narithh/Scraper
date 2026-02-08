# Copyright (C) 2026 Nikola
# This file is part of the "Scraper" project and is licensed under the
# GNU General Public License version 3 (GPLv3). See the LICENSE.txt file
# in the repository root for the full license text and obligations.

"""DuckDuckGo scraper that captures readable text from top results.

The script intentionally refrains from bypassing bot-detection systems: whenever a
captcha or suspicious page is detected, it prints a clear message and exits so the
user knows why scraping stopped.
"""

import argparse
import sys
import time
import random
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from readability import Document
from bs4 import BeautifulSoup


class CaptchaDetectedError(Exception):
    """Raised when a captcha or bot-detection page blocks automation."""


# When False the script is silent except for stderr messages. Set in main().
VERBOSE = False


def vprint(*args, **kwargs):
    """Print only when VERBOSE is True. Keeps stderr prints unchanged."""
    if VERBOSE:
        print(*args, **kwargs)


CAPTCHA_KEYWORDS = [
    "are you human",
    "verify you are human",
    "unusual traffic",
    "complete the captcha",
    "please verify",
    "captcha",
    "robot check",
    "security check",
]


CAPTCHA_SELECTORS = [
    '[id*="captcha" i]',
    '[class*="captcha" i]',
    "div.g-recaptcha",
    "div.h-captcha",
    'iframe[src*="recaptcha" i]',
    'iframe[src*="hcaptcha" i]',
]

def parse_args() -> argparse.Namespace:
    """Return parsed CLI arguments for the scraper."""

    parser = argparse.ArgumentParser(
        description="Search DuckDuckGo, scrape top results, and save cleaned text to markdown."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="best console editor for linux",
        help="Search query to use on DuckDuckGo (default: %(default)s).",
    )
    parser.add_argument(
        "-n",
        "--num-sites",
        type=int,
        default=3,
        help="Number of search results to scrape (default: %(default)s).",
    )
    parser.add_argument(
        "-m",
        "--max-words",
        type=int,
        default=1000,
        help="Maximum number of words to keep from each site (default: %(default)s).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.md"),
        help="Markdown file to write results to (default: %(default)s).",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the output file instead of overwriting.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (default is headed).",
    )
    parser.add_argument(
        "--verbatim",
        action="store_true",
        help="Enable verbose (printed) output. By default the scraper is silent and only writes errors to stderr.",
    )
    return parser.parse_args()

def is_captcha_page(page) -> bool:
    """Heuristic detection for captcha or bot-detection screens."""

    try:
        body_text = page.inner_text("body").lower()
    except Exception:
        body_text = ""

    if any(keyword in body_text for keyword in CAPTCHA_KEYWORDS):
        return True

    for selector in CAPTCHA_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue

    return False


def raise_captcha(context: str, hint: Optional[str] = None) -> None:
    """Raise a CaptchaDetectedError with consistent messaging."""

    message = f"    Captcha (or bot detection) encountered on {context}."
    if hint:
        message += f" {hint}"
    raise CaptchaDetectedError(message)


def ensure_not_captcha(page, context: str) -> None:
    """Guard clause that exits early if the current page looks like a captcha."""

    if is_captcha_page(page):
        raise_captcha(context)


def human_delay(min_ms: int = 200, max_ms: int = 600) -> None:
    """Sleep for a random interval to mimic human browsing."""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def extract_main_text(html: str) -> Optional[str]:
    """Return the main readable content from raw HTML using readability +
    BeautifulSoup.

    This is a small adapter around readability.Document and BeautifulSoup
    that returns the cleaned plain-text body or None if nothing useful was
    extracted.
    """

    doc = Document(html)
    cleaned_html = doc.summary()
    soup = BeautifulSoup(cleaned_html, "html.parser")
    cleaned_text = soup.get_text(separator="\n", strip=True)
    return cleaned_text or None


def fetch_search_results(page, query: str, num_sites: int) -> List[str]:
    """Perform the DuckDuckGo query and return absolute URLs for the top results."""

    search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
    vprint(f"Searching DuckDuckGo for: {query}")
    # First try the standard DuckDuckGo search. If that appears to be a
    # bot-detection/captcha page, fall back to the lightweight HTML-only
    # endpoint which is less likely to trigger bot protection.
    try:
        page.goto(search_url, wait_until="domcontentloaded")
        # Bot-detection screens often load in-place, so check immediately after navigation.
        ensure_not_captcha(page, "DuckDuckGo search page")
        human_delay()
        page.wait_for_selector('a[data-testid="result-title-a"]', timeout=5000)
        locator = page.locator('a[data-testid="result-title-a"]')
    except (PlaywrightTimeoutError, CaptchaDetectedError):
        # Attempt the HTML-only search page as a fallback.
        try:
            html_search = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
            page.goto(html_search, wait_until="domcontentloaded")
            ensure_not_captcha(page, "DuckDuckGo HTML search page")
            human_delay()
            # The HTML version uses different classes; fall back to parsing anchors.
            locator = page.locator('a')
        except Exception:
            raise_captcha(
                "DuckDuckGo search page",
                hint="Timed out waiting for results or blocked by captcha.",
            )
    results = []
    try:
        count = locator.count()
    except Exception:
        count = 0

    for idx in range(count):
        if len(results) >= num_sites:
            break
        try:
            href = locator.nth(idx).get_attribute("href")
        except Exception:
            href = None
        if not href:
            # As a last resort parse href from the element's outerHTML
            try:
                outer = locator.nth(idx).inner_html()
            except Exception:
                outer = ""
            # crude skip if no href; continue
            continue
        # filter out DuckDuckGo-internal links
        if href.startswith("/") or "duckduckgo.com" in href:
            continue
        results.append(href)

    if not results:
        print("No results were found on the DuckDuckGo page.", file=sys.stderr)
    else:
        vprint(f"Found {len(results)} result(s).")

    return results


def scrape_page(page, url: str, max_words: int) -> Optional[str]:
    """Navigate to an article page, extract readable text, and truncate to max_words."""
    # Try to load the page with a single retry on timeout. If a captcha
    # or bot-detection is detected we treat this page as skipped (return None)
    # so the caller can continue with remaining results.
    vprint(f"Opening {url}")
    html = None
    for attempt in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded")
            # immediate captcha check after navigation
            ensure_not_captcha(page, url)
            human_delay()
            html = page.content()
            ensure_not_captcha(page, url)
            break
        except PlaywrightTimeoutError:
            # retry once with a longer human-like delay
            if attempt == 0:
                human_delay(500, 1500)
                continue
            # final timeout: check if it's a captcha, otherwise skip
            try:
                ensure_not_captcha(page, url)
            except CaptchaDetectedError:
                return None
            return None
        except CaptchaDetectedError:
            return None
        except Exception as exc:
            # Some other navigation error; ensure it's not a captcha then skip
            try:
                ensure_not_captcha(page, url)
            except CaptchaDetectedError:
                return None
            print(f"Failed to load {url}: {exc}", file=sys.stderr)
            return None

    if not html:
        vprint(f"No HTML captured from {url}; skipping.")
        return None

    text = extract_main_text(html)
    if not text:
        vprint(f"Could not extract readable content from {url}")
        return None

    return truncate_words(text, max_words)


def write_markdown(output_path: Path, results: List[tuple], append: bool) -> None:
    """Persist results to the target markdown file, optionally appending."""

    mode = "a" if append else "w"
    with output_path.open(mode, encoding="utf-8") as f:
        for idx, (url, text) in enumerate(results):
            f.write(f"## {url}\n\n")
            f.write(f"{text}\n\n")
            if idx < len(results) - 1:
                f.write("---\n\n")


class DDGScraper:
    """DuckDuckGo scraper encapsulated as a class.

    This class wraps the existing procedural functions and provides a
    run() method so the script entrypoint can be as simple as
    DDGScraper(args).run(). The class sets the global verbosity flag so
    existing helper functions that call vprint() continue to work.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        """Initialize the scraper with parsed CLI arguments.

        The constructor stores configuration and prepares result
        containers.
        """
        self.args = args
        # Set module-level VERBOSE so existing helper functions honor verbosity.
        global VERBOSE
        VERBOSE = bool(getattr(args, "verbatim", False))

        self.scraped_results: List[tuple] = []
        self.skipped_urls: List[str] = []
        self.browser = None
        self.page = None

    def run(self) -> int:
        """Run the full scraping flow.

        Returns 0 on success (some pages scraped) or 1 on failure.
        """
        # basic validation
        if self.args.num_sites <= 0:
            print("--num-sites must be greater than 0", file=sys.stderr)
            return 1
        if self.args.max_words <= 0:
            print("--max-words must be greater than 0", file=sys.stderr)
            return 1

        try:
            with sync_playwright() as p:
                # Launch browser according to requested mode
                self.browser = p.chromium.launch(
                    headless=self.args.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self.page = self.browser.new_page()

                try:
                    urls = fetch_search_results(self.page, self.args.query, self.args.num_sites)
                    if not urls:
                        self._close_browser()
                        return 1

                    for url in urls:
                        text = scrape_page(self.page, url, self.args.max_words)
                        if text:
                            self.scraped_results.append((url, text))
                        else:
                            self.skipped_urls.append(url)

                    if not self.scraped_results:
                        print(
                            "No content could be scraped from the selected sites.",
                            file=sys.stderr,
                        )
                        self._close_browser()
                        return 1

                    write_markdown(self.args.output, self.scraped_results, self.args.append)
                    vprint(f"Saved {len(self.scraped_results)} entr(ies) to {self.args.output}")
                    if self.skipped_urls:
                        vprint(
                            f"Skipped {len(self.skipped_urls)} URL(s) due to captcha or errors:",
                            file=sys.stderr,
                        )
                        for s in self.skipped_urls:
                            vprint(f"  - {s}", file=sys.stderr)

                except CaptchaDetectedError as exc:
                    print(str(exc), file=sys.stderr)
                    print(
                        "The scraper was likely blocked by a captcha challenge. Exiting without attempting to solve it.",
                        file=sys.stderr,
                    )
                    self._close_browser()
                    return 1
                finally:
                    self._close_browser()

        except Exception as exc:
            print(f"Unexpected error: {exc}", file=sys.stderr)
            return 1

        return 0

    def _close_browser(self) -> None:
        """Attempt to close the browser if it is open."""
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass

def main() -> None:
    """Entrypoint: parse arguments and run DDGScraper.

    The DDGScraper class contains the scraping logic; main() simply
    constructs it and exits with the class' return code.
    """

    args = parse_args()
    scraper = DDGScraper(args)
    rc = scraper.run()
    sys.exit(rc)


if __name__ == "__main__":
    main()