import asyncio
import json
import threading
import uuid
import requests
import zipfile
import io
import os
from urllib.parse import urlparse
from flask import Flask, render_template, request, jsonify, send_file
from scraper.crawler import Crawler
from scraper.extractor import Extractor
from scraper.organizer import Organizer

app = Flask(__name__)
tasks = {}


def run_scrape(task_id, url):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_scrape_task(task_id, url))
    finally:
        loop.close()


async def _scrape_task(task_id, url):
    task = tasks[task_id]
    task["status"] = "crawling"
    task["pages_scraped"] = 0
    task["files_found"] = 0
    task["errors"] = 0

    crawler = Crawler(url)

    def progress(**kwargs):
        t = kwargs.get("type", "")
        if t == "page_scraped":
            task["pages_scraped"] = kwargs.get("total_pages", task["pages_scraped"] + 1)
            task["log"].append(f'Scraped: {kwargs["url"]}')
        elif t == "file_found":
            task["files_found"] = kwargs.get("total_discovered", task["files_found"] + 1)
        elif t == "discovered":
            task["discovered"] = kwargs.get("total_discovered", task.get("discovered", 0) + 1)
        elif t == "error":
            task["errors"] += 1
            task["log"].append(f'Error: {kwargs["url"]}')

    crawler.on_progress(progress)
    result = await crawler.run()
    if result is None:
        result = crawler.get_results()

    task["status"] = "extracting"
    task["log"].append("Extracting content...")

    extractor = Extractor(url)
    extracted_pages = []
    total = len(result["html_pages"])
    for i, (page_url, html) in enumerate(result["html_pages"].items()):
        extracted_pages.append(extractor.extract_page(page_url, html))
        task["extract_progress"] = f"{i+1}/{total}"

    task["status"] = "generating"
    task["log"].append("Generating reports...")

    organizer = Organizer()
    report = organizer.build_report(result, extracted_pages, url)
    json_path = organizer.save_json(report)
    html_path = organizer.save_html(report)

    task["report"] = report
    task["json_path"] = json_path
    task["html_path"] = html_path
    task["total_files"] = sum(len(v) for v in report.get("files", {}).values())
    task["status"] = "done"
    task["log"].append("Complete!")


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/scrape", methods=["POST"])
def start_scrape():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "starting",
        "url": url,
        "pages_scraped": 0,
        "files_found": 0,
        "discovered": 0,
        "errors": 0,
        "extract_progress": "",
        "total_files": 0,
        "log": [],
        "report": None,
        "json_path": None,
        "html_path": None,
    }

    t = threading.Thread(target=run_scrape, args=(task_id, url), daemon=True)
    t.start()
    return jsonify({"task_id": task_id})


@app.route("/status/<task_id>")
def get_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({
        "status": task["status"],
        "pages_scraped": task["pages_scraped"],
        "files_found": task["files_found"],
        "discovered": task["discovered"],
        "errors": task["errors"],
        "extract_progress": task["extract_progress"],
        "total_files": task["total_files"],
        "log": task["log"][-20:],
        "has_report": task["report"] is not None,
    })


@app.route("/report-data/<task_id>")
def report_data(task_id):
    task = tasks.get(task_id)
    if not task or not task["report"]:
        return jsonify({"error": "Report not found"}), 404
    return jsonify(task["report"])


@app.route("/report/<task_id>")
def view_report(task_id):
    task = tasks.get(task_id)
    if not task or not task["report"]:
        return "Report not found", 404
    return render_template(
        "report.html",
        stats=task["report"]["scrape_info"],
        pages=task["report"]["pages"],
        files=task["report"].get("files", {}),
        errors=task["report"].get("errors", []),
    )


@app.route("/download/<task_id>/<fmt>")
def download(task_id, fmt):
    task = tasks.get(task_id)
    if not task:
        return "Task not found", 404
    path = task.get(f"{fmt}_path")
    if not path or not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True)


@app.route("/download-all/<task_id>")
def download_all(task_id):
    task = tasks.get(task_id)
    if not task or not task["report"]:
        return "Report not found", 404

    files_by_category = task["report"].get("files", {})
    total = sum(len(v) for v in files_by_category.values())
    if total == 0:
        return jsonify({"error": "No files found"}), 404

    zip_buffer = io.BytesIO()
    downloaded = 0
    failed = 0
    visited = set()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for category, file_list in files_by_category.items():
            for f in file_list:
                url = f["url"]
                if url in visited:
                    continue
                visited.add(url)
                try:
                    resp = requests.get(url, timeout=15, headers={
                        "User-Agent": "Mozilla/5.0"
                    })
                    if resp.status_code == 200:
                        parsed = urlparse(url)
                        path = parsed.path.lstrip("/")
                        if not path:
                            path = f"file_{downloaded}"
                        zf.writestr(f"{category}/{path}", resp.content)
                        downloaded += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

    zip_buffer.seek(0)
    domain = task["report"]["scrape_info"]["domain"]
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{domain}_files.zip",
    )


if __name__ == "__main__":
    print("=" * 55)
    print("  WebScraper Dashboard")
    print("  Open http://localhost:8765 in your browser")
    print("  Press Ctrl+C to stop")
    print("=" * 55)
    app.run(host="127.0.0.1", port=8765, debug=False, threaded=True)
