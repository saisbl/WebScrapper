import json
from datetime import datetime
from pathlib import Path
from .utils import format_size, slugify


class Organizer:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, crawl_data: dict, extracted_data: dict, start_url: str) -> dict:
        report = {
            "scrape_info": {
                "start_url": start_url,
                "domain": crawl_data["stats"]["domain"],
                "scraped_at": datetime.now().isoformat(),
                "pages_scraped": crawl_data["stats"]["pages_scraped"],
                "files_found": crawl_data["stats"]["files_found"],
                "errors": crawl_data["stats"]["errors"],
            },
            "pages": extracted_data,
            "files": self._organize_files(crawl_data["file_urls"]),
            "errors": crawl_data["errors"],
        }
        return report

    def _organize_files(self, file_urls: list[str]) -> list[dict]:
        categorized = {"documents": [], "images": [], "media": [], "archives": [], "other": []}
        for url in file_urls:
            from .utils import is_document, is_image, is_media, is_archive

            ext = "." + url.rsplit(".", 1)[-1].lower() if "." in url else ""
            entry = {"url": url, "type": ext.lstrip(".").upper()}
            if is_document(url):
                categorized["documents"].append(entry)
            elif is_image(url):
                categorized["images"].append(entry)
            elif is_media(url):
                categorized["media"].append(entry)
            elif is_archive(url):
                categorized["archives"].append(entry)
            else:
                categorized["other"].append(entry)
        return categorized

    def save_json(self, report: dict, filename: str = None) -> str:
        name = filename or f"scrape_report_{slugify(report['scrape_info']['domain'])}.json"
        path = self.output_dir / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return str(path)

    def save_html(self, report: dict, filename: str = None) -> str:
        name = filename or f"scrape_report_{slugify(report['scrape_info']['domain'])}.html"
        path = self.output_dir / name

        pages_html = ""
        for page in report["pages"]:
            url = page["url"]
            meta = page["metadata"]
            headings_html = "".join(
                f'<li class="h-{h["level"]}">{h["level"].upper()}: {h["text"]}</li>' for h in page["headings"]
            )
            word_count = page.get("word_count", 0)

            links_count = page.get("links", {}).get("total", 0)
            images_count = len(page.get("images", []))
            docs_count = len(page.get("documents", []))
            tables_count = len(page.get("tables", []))

            pages_html += f"""
            <div class="page-card">
                <div class="page-header" onclick="this.nextElementSibling.classList.toggle('hidden')">
                    <h3>{meta['title'][:80] or url}</h3>
                    <span class="url">{url}</span>
                    <div class="stats-row">
                        <span>{word_count} words</span> |
                        <span>{links_count} links</span> |
                        <span>{images_count} images</span> |
                        <span>{docs_count} docs</span> |
                        <span>{tables_count} tables</span>
                    </div>
                </div>
                <div class="page-body hidden">
                    <div class="info-grid">
                        <div class="info-card">
                            <h4>Metadata</h4>
                            <p><strong>Title:</strong> {meta['title']}</p>
                            <p><strong>Description:</strong> {meta['description'][:200]}</p>
                            <p><strong>Keywords:</strong> {meta.get('keywords', 'N/A')}</p>
                            <p><strong>Language:</strong> {meta.get('language', 'N/A')}</p>
                        </div>
                        <div class="info-card">
                            <h4>Headings Structure</h4>
                            <ul>{headings_html}</ul>
                        </div>
                    </div>

                    <div class="info-card">
                        <h4>Text Preview ({word_count} words)</h4>
                        <div class="text-preview">{page['structured_text'][:1500]}...</div>
                    </div>

                    <div class="info-grid">
                        <div class="info-card">
                            <h4>Links ({links_count})</h4>
                            <p><strong>Internal:</strong> {len(page.get('links', {}).get('internal', []))}</p>
                            <p><strong>External:</strong> {len(page.get('links', {}).get('external', []))}</p>
                        </div>
                        <div class="info-card">
                            <h4>Images ({images_count})</h4>
                            {"".join(f'<p><img src="{img["src"]}" alt="{img["alt"]}" style="max-width:100px;max-height:100px;vertical-align:middle"/> {img["alt"][:50]}</p>' for img in page.get('images', [])[:5])}
                        </div>
                    </div>

                    <div class="info-grid">
                        <div class="info-card">
                            <h4>Documents ({docs_count})</h4>
                            <ul>{"".join(f'<li><a href="{d["url"]}" target="_blank">{d["text"]} ({d["type"]})</a></li>' for d in page.get('documents', []))}</ul>
                        </div>
                        <div class="info-card">
                            <h4>Tables ({tables_count})</h4>
                            {"".join(f'<p>Table with {t["row_count"]} rows</p>' for t in page.get('tables', []))}
                        </div>
                    </div>
                </div>
            </div>
            """

        file_info = report.get("files", {})
        files_html = ""
        for category, items in file_info.items():
            if items:
                files_html += f"""
                <div class="info-card">
                    <h4>{category.title()} ({len(items)})</h4>
                    <ul>{"".join(f'<li><a href="{f["url"]}" target="_blank">{f["type"]} file</a></li>' for f in items[:20])}</ul>
                    {"<p>..." if len(items) > 20 else ""}
                </div>
                """

        errors_html = ""
        for err in report.get("errors", []):
            errors_html += f'<li><strong>{err["url"]}</strong>: {err["error"]}</li>'

        html = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Scrape Report - {report['scrape_info']['domain']}</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; }}
                .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
                h1 {{ font-size: 2rem; color: #f8fafc; margin-bottom: 0.5rem; }}
                h2 {{ font-size: 1.5rem; color: #94a3b8; margin: 2rem 0 1rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
                .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
                .stat-card {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; text-align: center; }}
                .stat-card .number {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
                .stat-card .label {{ font-size: 0.875rem; color: #94a3b8; }}
                .page-card {{ background: #1e293b; border-radius: 12px; margin-bottom: 1rem; overflow: hidden; }}
                .page-header {{ padding: 1rem 1.25rem; cursor: pointer; }}
                .page-header:hover {{ background: #334155; }}
                .page-header h3 {{ font-size: 1.1rem; color: #f8fafc; }}
                .page-header .url {{ font-size: 0.8rem; color: #64748b; display: block; }}
                .page-header .stats-row {{ font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem; }}
                .page-body {{ padding: 1.25rem; }}
                .hidden {{ display: none; }}
                .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }}
                @media (max-width: 768px) {{ .info-grid {{ grid-template-columns: 1fr; }} }}
                .info-card {{ background: #0f172a; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
                .info-card h4 {{ font-size: 1rem; color: #38bdf8; margin-bottom: 0.75rem; }}
                .info-card ul {{ list-style: none; }}
                .info-card li, .info-card p {{ font-size: 0.875rem; color: #cbd5e1; margin-bottom: 0.25rem; }}
                .info-card li.h-h1 {{ font-weight: 700; }}
                .info-card li.h-h2 {{ padding-left: 1rem; font-weight: 600; }}
                .info-card li.h-h3 {{ padding-left: 2rem; }}
                .info-card a {{ color: #38bdf8; }}
                .text-preview {{ font-size: 0.875rem; color: #94a3b8; max-height: 200px; overflow-y: auto; white-space: pre-wrap; }}
                .error-list {{ background: #1e293b; border-radius: 12px; padding: 1.25rem; }}
                .error-list li {{ color: #f87171; margin-bottom: 0.5rem; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Web Scrape Report</h1>
                <p>Domain: {report['scrape_info']['domain']} | Scraped: {report['scrape_info']['scraped_at']}</p>

                <div class="summary">
                    <div class="stat-card"><div class="number">{report['scrape_info']['pages_scraped']}</div><div class="label">Pages Scraped</div></div>
                    <div class="stat-card"><div class="number">{report['scrape_info']['files_found']}</div><div class="label">Files Found</div></div>
                    <div class="stat-card"><div class="number">{len(report['pages'])}</div><div class="label">Extracted Pages</div></div>
                    <div class="stat-card"><div class="number">{report['scrape_info']['errors']}</div><div class="label">Errors</div></div>
                </div>

                {f'<h2>Files Found ({report["scrape_info"]["files_found"]})</h2><div class="info-grid">{files_html}</div>' if files_html else ''}

                <h2>Pages ({len(report['pages'])})</h2>
                {pages_html}

                {f'<h2>Errors ({len(report["errors"])})</h2><div class="error-list"><ul>{errors_html}</ul></div>' if errors_html else ''}
            </div>
            <script>
                document.querySelectorAll('.page-card').forEach(card => {{
                    card.querySelector('.page-header').addEventListener('click', () => {{
                        const body = card.querySelector('.page-body');
                        body.classList.toggle('hidden');
                    }});
                }});
            </script>
        </body>
        </html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return str(path)
