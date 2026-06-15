import asyncio
import aiohttp
from urllib.parse import urlparse
from collections import deque
from .utils import normalize_url, is_same_domain, get_domain, is_downloadable, format_size


class Crawler:
    def __init__(self, start_url: str, max_pages: int = 500, concurrency: int = 10, timeout: int = 30):
        self.start_url = start_url.rstrip("/")
        self.domain = get_domain(start_url)
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.timeout = timeout

        self.visited_html = set()
        self.visited_files = set()
        self.to_visit = deque()
        self.to_visit.append(start_url)

        self.html_pages = {}
        self.file_urls = []
        self.errors = []
        self.total_discovered = 1

        self._semaphore = None
        self._session = None
        self._progress_callback = None

    def on_progress(self, callback):
        self._progress_callback = callback

    def _report(self, **kwargs):
        if self._progress_callback:
            self._progress_callback(**kwargs)

    async def _fetch(self, url: str) -> tuple[int, str | None, dict]:
        try:
            async with self._semaphore:
                async with self._session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    },
                    ssl=False,
                ) as resp:
                    content_type = resp.headers.get("Content-Type", "").lower()
                    size = int(resp.headers.get("Content-Length", 0))
                    text = await resp.text() if "text/html" in content_type else None
                    return resp.status, text, {"content_type": content_type, "size": size}
        except Exception as e:
            return 0, None, {"error": str(e)}

    async def run(self):
        self._semaphore = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(limit=self.concurrency, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as self._session:
            while self.to_visit and len(self.visited_html) < self.max_pages:
                batch = []
                while self.to_visit and len(batch) < self.concurrency:
                    url = self.to_visit.popleft()
                    if url not in self.visited_html and url not in self.visited_files:
                        if is_downloadable(url):
                            self.visited_files.add(url)
                            self.file_urls.append(url)
                            self._report(type="file_found", url=url, total_discovered=len(self.file_urls))
                        else:
                            batch.append(url)

                if not batch:
                    continue

                tasks = [self._fetch(url) for url in batch]
                results = await asyncio.gather(*tasks)

                for url, (status, html, info) in zip(batch, results):
                    if html is not None and status == 200:
                        self.visited_html.add(url)
                        self.html_pages[url] = html
                        self._report(
                            type="page_scraped",
                            url=url,
                            size=info.get("size", 0),
                            total_pages=len(self.visited_html),
                        )
                        self._extract_links(url, html)
                    elif html is None and is_downloadable(url):
                        continue
                    else:
                        error = info.get("error", f"HTTP {status}")
                        self.errors.append({"url": url, "error": error})
                        self._report(type="error", url=url, error=error)

        self._report(type="done", total_pages=len(self.visited_html), total_files=len(self.file_urls))
        return self.get_results()

    def _extract_links(self, base_url: str, html: str):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            normalized = normalize_url(base_url, href)
            if normalized and is_same_domain(normalized, self.domain):
                if normalized not in self.visited_html and normalized not in {
                    u for u in self.to_visit
                }:
                    if is_downloadable(normalized):
                        if normalized not in self.visited_files:
                            self.visited_files.add(normalized)
                            self.file_urls.append(normalized)
                            self._report(type="file_found", url=normalized, total_discovered=len(self.file_urls))
                    else:
                        self.to_visit.append(normalized)
                        self.total_discovered += 1
                        self._report(type="discovered", url=normalized, total_discovered=self.total_discovered)

    def get_results(self):
        return {
            "html_pages": self.html_pages,
            "file_urls": self.file_urls,
            "errors": self.errors,
            "stats": {
                "pages_scraped": len(self.visited_html),
                "files_found": len(self.file_urls),
                "errors": len(self.errors),
                "domain": self.domain,
                "start_url": self.start_url,
            },
        }
