from urllib.parse import urlparse, urljoin
import re
from pathlib import Path

DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".csv", ".txt", ".rtf", ".odt", ".ods", ".odp",
    ".json", ".xml", ".yaml", ".yml", ".md",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff"}

MEDIA_EXTENSIONS = {".mp4", ".mp3", ".avi", ".mov", ".wmv", ".flv", ".webm", ".wav", ".ogg", ".m4a"}

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".rar", ".7z"}


def normalize_url(base: str, href: str) -> str | None:
    joined = urljoin(base, href)
    parsed = urlparse(joined)
    if parsed.scheme not in ("http", "https"):
        return None
    cleaned = parsed._replace(fragment="").geturl()
    return cleaned.rstrip("/")


def is_same_domain(url: str, base_domain: str) -> bool:
    try:
        return urlparse(url).netloc == base_domain
    except Exception:
        return False


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def get_file_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    return Path(path).suffix


def is_document(url: str) -> bool:
    return get_file_extension(url) in DOCUMENT_EXTENSIONS


def is_image(url: str) -> bool:
    return get_file_extension(url) in IMAGE_EXTENSIONS


def is_media(url: str) -> bool:
    return get_file_extension(url) in MEDIA_EXTENSIONS


def is_archive(url: str) -> bool:
    return get_file_extension(url) in ARCHIVE_EXTENSIONS


def is_downloadable(url: str) -> bool:
    ext = get_file_extension(url)
    return ext in DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | MEDIA_EXTENSIONS | ARCHIVE_EXTENSIONS


def format_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def slugify(text: str) -> str:
    return re.sub(r"[^\w\-_]", "_", text.lower()).strip("_")
