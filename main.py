import asyncio
import sys
from datetime import datetime
from scraper.crawler import Crawler
from scraper.extractor import Extractor
from scraper.organizer import Organizer
from scraper.display import Display
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.panel import Panel
from rich.console import Console


async def main():
    console = Console()

    if len(sys.argv) < 2:
        console.print("[red]Usage: python main.py <URL>[/]")
        console.print("[dim]Example: python main.py https://example.com[/]")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    display = Display()
    display.print_banner()
    display.print_start(url)

    crawler = Crawler(url)

    layout = Layout()
    layout.split_column(Layout(name="main", size=12), Layout(name="footer", size=3))
    layout["main"].split_row(Layout(name="stats"), Layout(name="activity"))

    with Live(layout, refresh_per_second=4, screen=False) as live:

        def handle_progress(**kwargs):
            display.handle_event(**kwargs)
            layout["main"]["stats"].update(display.get_progress_table())
            layout["main"]["activity"].update(display.get_activity_panel())
            elapsed = datetime.now() - display.start_time
            footer_text = (
                f"WebScraper - {display.stats['pages_scraped']} pages - "
                f"{display.stats['files_found']} files - "
                f"{elapsed.seconds // 60}m {elapsed.seconds % 60}s"
            )
            layout["footer"].update(Panel(Text(footer_text, style="dim"), border_style="dim"))

        crawler.on_progress(handle_progress)
        result = await crawler.run()
        if result is None:
            result = crawler.get_results()

    display.print_summary({"scrape_info": result["stats"]})
    console.print("[bold cyan]Extracting content from all pages...[/]")

    extractor = Extractor(url)
    extracted_pages = []
    for page_url, html in result["html_pages"].items():
        extracted = extractor.extract_page(page_url, html)
        extracted_pages.append(extracted)

    console.print(f"[green]Extracted content from {len(extracted_pages)} pages[/]")
    console.print("[bold cyan]Generating output files...[/]")

    organizer = Organizer()
    report = organizer.build_report(result, extracted_pages, url)

    json_path = organizer.save_json(report)
    html_path = organizer.save_html(report)

    console.print(f"\n[bold green]+ Scraping completed successfully![/]")
    console.print(f"  JSON report: [cyan]{json_path}[/]")
    console.print(f"  HTML report: [cyan]{html_path}[/]")
    console.print()

    display.print_summary(report)

    files = report.get("files", {})
    if any(files.values()):
        console.print("[bold]Files found by category:[/]")
        for category, items in files.items():
            if items:
                console.print(f"  [yellow]{category.title()}:[/] {len(items)}")
        console.print()


if __name__ == "__main__":
    asyncio.run(main())
