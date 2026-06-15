from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from .utils import normalize_url, is_same_domain, get_domain
import re


class Extractor:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.domain = get_domain(base_url)

    def extract_page(self, url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        metadata = self._extract_metadata(soup, url)
        headings = self._extract_headings(soup)
        paragraphs = self._extract_paragraphs(soup)
        links = self._extract_links(soup, url)
        images = self._extract_images(soup, url)
        media = self._extract_media(soup, url)
        documents = self._extract_documents(soup, url)
        tables = self._extract_tables(soup)
        lists_data = self._extract_lists(soup)
        code_blocks = self._extract_code_blocks(soup)
        structured_text = self._extract_structured_text(soup)

        return {
            "url": url,
            "metadata": metadata,
            "headings": headings,
            "paragraphs": paragraphs,
            "links": links,
            "images": images,
            "media": media,
            "documents": documents,
            "tables": tables,
            "lists": lists_data,
            "code_blocks": code_blocks,
            "structured_text": structured_text,
            "word_count": len(structured_text.split()),
            "char_count": len(structured_text),
        }

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        title = ""
        if soup.title:
            title = soup.title.string.strip() if soup.title.string else ""

        description = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            description = og_desc["content"]
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"]

        keywords = ""
        meta_kw = soup.find("meta", attrs={"name": "keywords"})
        if meta_kw and meta_kw.get("content"):
            keywords = meta_kw["content"]

        og_image = ""
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            og_image = og_img["content"]

        lang = soup.html.get("lang", "") if soup.html else ""

        return {
            "title": title.strip(),
            "description": description.strip(),
            "keywords": keywords.strip(),
            "og_image": og_image,
            "language": lang,
            "url": url,
        }

    def _extract_headings(self, soup: BeautifulSoup) -> list[dict]:
        headings = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = tag.get_text(strip=True)
            if text:
                headings.append({"level": tag.name, "text": text})
        return headings

    def _extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        return [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> dict:
        internal = []
        external = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            normalized = normalize_url(base_url, href)
            if not normalized:
                continue
            link_info = {"url": normalized, "text": text or "(no text)"}
            if is_same_domain(normalized, self.domain):
                internal.append(link_info)
            else:
                external.append(link_info)
        return {"internal": internal, "external": external, "total": len(internal) + len(external)}

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        images = []
        seen = set()
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src:
                continue
            full_url = urljoin(base_url, src.strip())
            if full_url in seen:
                continue
            seen.add(full_url)
            images.append(
                {
                    "src": full_url,
                    "alt": img.get("alt", "").strip(),
                    "title": img.get("title", "").strip(),
                    "width": img.get("width", ""),
                    "height": img.get("height", ""),
                }
            )
        return images

    def _extract_media(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        media = []
        for tag in soup.find_all(["video", "audio", "source"]):
            src = tag.get("src")
            if src:
                media.append({"src": urljoin(base_url, src.strip()), "type": tag.name})
        for source in soup.find_all("source", src=True):
            src = source.get("src")
            if src:
                type_ = source.get("type", "unknown")
                media.append({"src": urljoin(base_url, src.strip()), "type": type_})
        return media

    def _extract_documents(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        from .utils import is_document, DOCUMENT_EXTENSIONS

        docs = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full_url = urljoin(base_url, href)
            if full_url in seen:
                continue
            ext = "." + full_url.rsplit(".", 1)[-1].lower() if "." in full_url else ""
            if ext in DOCUMENT_EXTENSIONS:
                seen.add(full_url)
                docs.append(
                    {
                        "url": full_url,
                        "type": ext.lstrip(".").upper(),
                        "text": a.get_text(strip=True) or "(no text)",
                    }
                )
        return docs

    def _extract_tables(self, soup: BeautifulSoup) -> list[dict]:
        tables = []
        for table in soup.find_all("table"):
            rows = []
            headers = []
            for th in table.find_all("th"):
                headers.append(th.get_text(strip=True))
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append({"headers": headers, "rows": rows, "row_count": len(rows)})
        return tables

    def _extract_lists(self, soup: BeautifulSoup) -> list[dict]:
        lists_data = []
        for list_tag in soup.find_all(["ul", "ol"]):
            items = [li.get_text(strip=True) for li in list_tag.find_all("li") if li.get_text(strip=True)]
            if items:
                lists_data.append({"type": list_tag.name, "items": items})
        return lists_data

    def _extract_code_blocks(self, soup: BeautifulSoup) -> list[dict]:
        blocks = []
        for code in soup.find_all("code"):
            text = code.get_text()
            if text.strip():
                blocks.append({"language": code.get("class", [""])[0] if code.get("class") else "", "code": text.strip()})
        for pre in soup.find_all("pre"):
            text = pre.get_text()
            if text.strip():
                code_tag = pre.find("code")
                lang = ""
                if code_tag and code_tag.get("class"):
                    lang = code_tag["class"][0]
                blocks.append({"language": lang, "code": text.strip()})
        return blocks

    def _extract_structured_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
