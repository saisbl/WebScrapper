import asyncio
import io
import json
import threading
import uuid
import zipfile
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from scraper.crawler import Crawler
from scraper.extractor import Extractor
from scraper.organizer import Organizer

app = Flask(__name__)
tasks = {}
BASE_DIR = Path(__file__).parent


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
    task["files_downloaded"] = 0
    task["files_failed"] = 0

    files_dir = BASE_DIR / "output" / task_id / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    crawler = Crawler(url, files_dir=str(files_dir))

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

    task["total_files"] = result["stats"]["files_found"]
    task["files_downloaded"] = result["stats"]["files_downloaded"]
    task["files_failed"] = task["total_files"] - task["files_downloaded"]

    json_path = organizer.save_json(report)
    html_path = organizer.save_html(report)

    task["files_dir"] = str(files_dir)
    task["report"] = report
    task["json_path"] = json_path
    task["html_path"] = html_path
    task["status"] = "done"
    task["log"].append(f"Complete! {task['files_downloaded']} files downloaded, {task['files_failed']} failed")


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
        "files_downloaded": 0,
        "files_failed": 0,
        "download_progress": "",
        "extract_progress": "",
        "total_files": 0,
        "log": [],
        "report": None,
        "json_path": None,
        "html_path": None,
        "files_dir": None,
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
        "files_downloaded": task["files_downloaded"],
        "files_failed": task["files_failed"],
        "download_progress": task["download_progress"],
        "extract_progress": task["extract_progress"],
        "total_files": task["total_files"],
        "log": task["log"][-30:],
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
    if not task:
        return "Task not found", 404

    files_dir = task.get("files_dir")
    if not files_dir or not os.path.isdir(files_dir):
        return jsonify({"error": "No downloaded files"}), 404

    zip_buffer = io.BytesIO()
    total_added = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(files_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, files_dir)
                zf.write(file_path, rel_path)
                total_added += 1

    if total_added == 0:
        return jsonify({"error": "No files found"}), 404

    zip_buffer.seek(0)
    domain = task.get("report", {}).get("scrape_info", {}).get("domain", "scrape")
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
