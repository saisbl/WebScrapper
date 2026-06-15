import asyncio
import os
import aiohttp
from urllib.parse import urlparse
from collections import deque
from pathlib import Path
from .utils import normalize_url, is_same_domain, get_domain, is_downloadable, format_size


FILE_CATEGORIES = {
    ".pdf": "documents", ".doc": "documents", ".docx": "documents",
    ".xls": "documents", ".xlsx": "documents", ".ppt": "documents",
    ".pptx": "documents", ".csv": "documents", ".txt": "documents",
    ".rtf": "documents", ".odt": "documents", ".json": "documents",
    ".xml": "documents", ".md": "documents",
    ".jpg": "images", ".jpeg": "images", ".png": "images",
    ".gif": "images", ".svg": "images", ".webp": "images",
    ".bmp": "images", ".ico": "images", ".tiff": "images",
    ".mp4": "media", ".mp3": "media", ".avi": "media",
    ".mov": "media", ".wmv": "media", ".flv": "media",
    ".webm": "media", ".wav": "media", ".ogg": "media",
    ".zip": "archives", ".tar": "archives", ".gz": "archives",
    ".rar": "archives", ".7z": "archives",
}


class Crawler:
    def __init__(self, start_url: str, max_pages: int = 500, concurrency: int = 10, timeout: int = 30, files_dir: str | None = None):
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
        self.files_map = {}

        self._semaphore = None
        self._session = None
        self._progress_callback = None
        self._files_dir = Path(files_dir) if files_dir else None

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

            await self._download_files()

        self._report(type="done", total_pages=len(self.visited_html), total_files=len(self.file_urls))
        return self.get_results()

    @staticmethod
    def _get_category(url: str) -> str:
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        return FILE_CATEGORIES.get(ext, "other")

    async def _download_files(self):
        if not self._files_dir or not self.file_urls:
            return

        sem = asyncio.Semaphore(10)

        async def _dl_one(file_url: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    async with self._session.get(
                        file_url,
                        timeout=aiohttp.ClientTimeout(total=30),
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        ssl=False,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            category = self._get_category(file_url)
                            parsed = urlparse(file_url)
                            rel_path = parsed.path.lstrip("/")
                            if not rel_path:
                                rel_path = f"file_{hash(file_url)}"
                            save_path = self._files_dir / category / rel_path
                            save_path.parent.mkdir(parents=True, exist_ok=True)
                            save_path.write_bytes(data)
                            return file_url, str(save_path)
                        return file_url, None
                except Exception:
                    return file_url, None

        tasks = [_dl_one(url) for url in self.file_urls]
        results = await asyncio.gather(*tasks)
        self.files_map = {url: path for url, path in results if path is not None}

    def _extract_links(self, base_url: str, html: str):
        from bs4 import BeautifulSoup
        from .utils import get_file_extension, IMAGE_EXTENSIONS, MEDIA_EXTENSIONS, DOCUMENT_EXTENSIONS, ARCHIVE_EXTENSIONS

        soup = BeautifulSoup(html, "lxml")

        # Check <a href> for both pages and downloadable files
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

        # Check <img src> and <img data-src> for images
        for tag in soup.find_all("img", src=True):
            for attr in ("src", "data-src"):
                src = tag.get(attr)
                if src:
                    normalized = normalize_url(base_url, src.strip())
                    if normalized and is_same_domain(normalized, self.domain) and normalized not in self.visited_files:
                        ext = get_file_extension(normalized)
                        if ext in IMAGE_EXTENSIONS:
                            self.visited_files.add(normalized)
                            self.file_urls.append(normalized)
                            self._report(type="file_found", url=normalized, total_discovered=len(self.file_urls))

        # Check <video>, <audio>, <source> for media
        for tag in soup.find_all(["video", "audio", "source"], src=True):
            src = tag.get("src")
            if src:
                normalized = normalize_url(base_url, src.strip())
                if normalized and is_same_domain(normalized, self.domain) and normalized not in self.visited_files:
                    self.visited_files.add(normalized)
                    self.file_urls.append(normalized)
                    self._report(type="file_found", url=normalized, total_discovered=len(self.file_urls))

    def get_results(self):
        return {
            "html_pages": self.html_pages,
            "file_urls": self.file_urls,
            "files_map": self.files_map,
            "files_dir": str(self._files_dir) if self._files_dir else None,
            "errors": self.errors,
            "stats": {
                "pages_scraped": len(self.visited_html),
                "files_found": len(self.file_urls),
                "files_downloaded": len(self.files_map),
                "errors": len(self.errors),
                "domain": self.domain,
                "start_url": self.start_url,
            },
        }
