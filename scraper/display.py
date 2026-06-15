from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich import box
from datetime import datetime
import sys


class Display:
    def __init__(self):
        self.console = Console(force_terminal=True)
        self.start_time = datetime.now()
        self.stats = {
            "pages_scraped": 0,
            "files_found": 0,
            "discovered": 0,
            "errors": 0,
            "current_url": "",
            "status": "Initializing...",
        }
        self.recent_activity = []

    def get_progress_table(self) -> Table:
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Metric", style="cyan", width=16)
        table.add_column("Value", style="white")

        elapsed = datetime.now() - self.start_time
        elapsed_str = f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s"

        table.add_row("Status", self.stats["status"])
        table.add_row("Pages scraped", str(self.stats["pages_scraped"]))
        table.add_row("Files found", str(self.stats["files_found"]))
        table.add_row("URLs discovered", str(self.stats["discovered"]))
        table.add_row("Errors", str(self.stats["errors"]))
        table.add_row("Elapsed", elapsed_str)
        return table

    def get_activity_panel(self) -> Panel:
        items = "\n".join(self.recent_activity[-8:]) if self.recent_activity else "  Waiting for activity..."
        return Panel(items, title="Activity Log", border_style="dim")

    def print_banner(self):
        banner = """
+----------------------------------------------+
|           WebScraper Engine v1.0              |
|    Full-site extraction & analysis tool       |
+----------------------------------------------+"""
        self.console.print(banner, style="bold blue")
        self.console.print()

    def print_start(self, url: str):
        self.console.print(f"[bold green]Starting scrape of:[/] {url}")
        self.console.print(f"[dim]Max concurrency: 10 | Timeout: 30s | Max pages: 500[/]")
        self.console.print()

    def build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(Layout(name="top", size=12), Layout(name="bottom"))
        layout["top"].split_row(Layout(name="stats"), Layout(name="activity"))
        layout["stats"].update(self.get_progress_table())
        layout["activity"].update(self.get_activity_panel())

        elapsed = datetime.now() - self.start_time
        footer = Text(
            f"WebScraper - {self.stats['pages_scraped']} pages - {self.stats['files_found']} files - "
            f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s",
            style="dim",
        )
        layout["bottom"].update(Panel(footer, border_style="dim"))
        return layout

    def handle_event(self, **kwargs):
        event_type = kwargs.get("type", "")

        if event_type == "page_scraped":
            self.stats["pages_scraped"] += 1
            url = kwargs.get("url", "")
            size = kwargs.get("size", 0)
            self.stats["current_url"] = url
            self.stats["status"] = "Scraping..."
            self.recent_activity.append(f"[green]+[/] {url} ({size // 1024}KB)")

        elif event_type == "file_found":
            self.stats["files_found"] += 1
            url = kwargs.get("url", "")
            self.recent_activity.append(f"[yellow][FILE][/] {url}")

        elif event_type == "discovered":
            self.stats["discovered"] += 1
            url = kwargs.get("url", "")

        elif event_type == "error":
            self.stats["errors"] += 1
            url = kwargs.get("url", "")
            error = kwargs.get("error", "")
            self.recent_activity.append(f"[red]ERR[/] {url} ({error})")

        elif event_type == "done":
            self.stats["status"] = "[bold green]Completed![/]"
            self.recent_activity.append(f"[bold green]Scraping complete![/]")

    def print_summary(self, report: dict):
        info = report["scrape_info"]
        elapsed = datetime.now() - self.start_time

        summary = Table(box=box.ROUNDED, title="Scrape Summary", title_style="bold cyan")
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="white")
        summary.add_row("Domain", info["domain"])
        summary.add_row("Pages scraped", str(info["pages_scraped"]))
        summary.add_row("Files found", str(info["files_found"]))
        summary.add_row("Errors encountered", str(info["errors"]))
        summary.add_row("Time elapsed", f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s")
        self.console.print(summary)
        self.console.print()
