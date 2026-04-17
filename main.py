import atexit
import html
import os
import re
import shutil
import sys
import tempfile

import niquests
from patchright.sync_api import Page, sync_playwright
from tqdm import tqdm

# -----------------------------
# config
# -----------------------------
PENDING_DIR = "pending"
ARTISTS_DIR = "artists"
ARTIST_LIST_FILE = "artists.txt"
COOKIE_FILE = "cookies.txt"
USER_AGENT_FILE = "user_agent.txt"
VIDEOS_PER_PAGE = 128
CLOUDFLARE_TITLE = "<title>Just a moment...</title>"


# -----------------------------
# filesystem
# -----------------------------
def ensure_dir(path: str) -> None:
    """Create a directory if needed."""
    os.makedirs(path, exist_ok=True)


def clear_dir(path: str) -> None:
    """Remove everything inside a directory."""
    ensure_dir(path)

    for name in os.listdir(path):
        item_path = os.path.join(path, name)

        try:
            if os.path.isdir(item_path) and not os.path.islink(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)
        except OSError as e:
            print(f"Could not remove: {item_path} ({e})")


def read_lines(path: str) -> list[str]:
    """Read non-empty non-comment lines from a file."""
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as file:
        return [
            line.strip()
            for line in file
            if line.strip() and not line.strip().startswith("#")
        ]


def write_lines(path: str, lines: list[str]) -> None:
    """Write lines to a file."""
    with open(path, "w", encoding="utf-8") as file:
        for line in lines:
            file.write(f"{line}\n")


# -----------------------------
# html parsing
# -----------------------------
def extract_video_links(page_html: str) -> list[str]:
    """Extract video page links."""
    pattern = r'<a[^>]+class="[^"]*ui-card-link[^"]*"[^>]+href="([^"]+)"'
    return re.findall(pattern, page_html)


def extract_video_id(page_html: str) -> str | None:
    """Extract the video id."""
    match = re.search(r"videoId:\s*'(\d+)'", page_html)
    return match.group(1) if match else None


def extract_artist_name(page_html: str) -> str | None:
    """Extract the artist name."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.DOTALL)
    if not match:
        return None

    return html.unescape(match.group(1)).strip()


def extract_page_count(page_html: str, artist_url: str) -> int:
    """Extract the number of artist pages."""
    artist_slug = artist_url.rstrip("/").split("/")[-1]
    pattern = rf'href="[^"]*{artist_slug}/(\d+)(?:/)?(?:\?[^"]*)?"[^>]*>(\d+)</a>'
    numbers = [int(number) for _, number in re.findall(pattern, page_html)]
    return max(numbers) if numbers else 1


def extract_mp4_urls(page_html: str) -> list[str]:
    """Extract valid mp4 urls."""
    raw_urls = re.findall(r"https?://[^\s'\"]+\.mp4[^\s'\"]*", page_html)
    unique_by_name: dict[str, str] = {}

    for url in raw_urls:
        url = url.replace("function/0/", "")

        if "_preview" in url:
            continue
        if ".jpg" in url:
            continue

        match = re.search(r"/([^/?]+\.mp4)", url)
        if not match:
            continue

        file_name = match.group(1)
        unique_by_name[file_name] = url

    return list(unique_by_name.values())


def get_best_quality_mp4(
    urls: list[str],
    cap_at_1080p: bool = True,
) -> str | None:
    """Pick the highest quality mp4."""
    candidates: list[tuple[int, str]] = []

    for url in urls:
        match = re.search(r"_(\d{3,4})p\.mp4", url)
        if not match:
            continue

        quality = int(match.group(1))

        if cap_at_1080p and quality > 1080:
            continue

        candidates.append((quality, url))

    if not candidates:
        return None

    candidates.sort()
    return candidates[-1][1]


# -----------------------------
# cookies
# -----------------------------
def save_cookies_netscape(cookies: list[dict], path: str) -> None:
    """Save cookies in Netscape format."""
    lines = ["# Netscape HTTP Cookie File"]

    for cookie in cookies:
        domain = cookie.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        cookie_path = cookie.get("path", "/")
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"
        expires = cookie.get("expires")

        if expires in (-1, None):
            expires = 0
        else:
            expires = int(expires)

        name = cookie.get("name", "")
        value = cookie.get("value", "")

        lines.append(
            "\t".join(
                [
                    domain,
                    include_subdomains,
                    cookie_path,
                    secure,
                    str(expires),
                    name,
                    value,
                ]
            )
        )

    write_lines(path, lines)


def load_cookies_netscape(path: str) -> list[dict]:
    """Load cookies from Netscape format."""
    cookies: list[dict] = []

    if not os.path.exists(path):
        return cookies

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain, _, cookie_path, secure, expires, name, value = parts[:7]

            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie_path,
                "secure": secure == "TRUE",
            }

            if expires.isdigit():
                cookie["expires"] = int(expires)

            cookies.append(cookie)

    return cookies


def get_cf_clearance(path: str = COOKIE_FILE) -> str | None:
    """Read cf_clearance from the cookie file."""
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] == "cf_clearance":
                return parts[6]

    return None


# -----------------------------
# browser helpers
# -----------------------------
def wait_for_cloudflare(page: Page, attempts: int = 10, delay_ms: int = 5000) -> str:
    """Wait until the Cloudflare page is gone."""
    page_html = page.content()

    for _ in range(attempts):
        if CLOUDFLARE_TITLE not in page_html:
            break

        print("Cloudflare protection detected, waiting 5 seconds...")
        page.wait_for_timeout(delay_ms)
        page_html = page.content()

    return page_html


def open_page(page: Page, url: str) -> str:
    """Open a page and return the final html."""
    page.goto(url)
    return wait_for_cloudflare(page)


def save_session_data(page: Page) -> str:
    """Save browser session cookies and user agent."""
    user_agent = page.evaluate("() => navigator.userAgent")

    with open(USER_AGENT_FILE, "w", encoding="utf-8") as file:
        file.write(user_agent)

    cookies = page.context.cookies()
    save_cookies_netscape(cookies, COOKIE_FILE)

    print(f"Saved user agent to {USER_AGENT_FILE}")
    print(f"Saved cookies to {COOKIE_FILE}")

    return user_agent


def make_page(browser, cookie_path: str) -> Page:
    """Create a page with optional saved cookies."""
    if os.path.exists(cookie_path):
        context = browser.new_context()
        context.add_cookies(load_cookies_netscape(cookie_path))
        print("Loaded saved cookies from previous session")
        return context.new_page()

    print("No cookies.txt found - starting fresh")
    return browser.new_page()


# -----------------------------
# downloads
# -----------------------------
def build_headers(user_agent: str, cookies: list[dict] | None = None) -> dict:
    """Build request headers."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "DNT": "1",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "TE": "trailers",
    }

    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    return headers


def download_file(
    stream_url: str,
    output_path: str,
    user_agent: str,
    cookies: list[dict] | None = None,
    timeout: int = 60,
) -> bool:
    """Download a file to disk."""
    headers = build_headers(user_agent, cookies)
    output_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    file_name = os.path.basename(output_path)

    fd, temp_path = tempfile.mkstemp(
        prefix=f"{file_name}.",
        suffix=".temp",
        dir=output_dir,
    )
    os.close(fd)

    try:
        with niquests.get(
            stream_url,
            headers=headers,
            stream=True,
            timeout=timeout,
        ) as response:
            response.raise_for_status()

            content_length = response.headers.get(
                "Content-Length"
            ) or response.headers.get("content-length")
            total = (
                int(content_length)
                if content_length and content_length.isdigit()
                else None
            )

            with open(temp_path, "wb") as file:
                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=file_name,
                    leave=True,
                ) as progress:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue

                        file.write(chunk)
                        progress.update(len(chunk))

        os.replace(temp_path, output_path)
        return True

    except Exception as e:
        print(f"Download failed for {stream_url}: {e}")

        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

        return False


# -----------------------------
# scraping
# -----------------------------
def get_artist_page_url(artist_url: str, page_number: int, per_page: int) -> str:
    """Build an artist page url."""
    base = artist_url.rstrip("/")

    if page_number == 1:
        return f"{base}/?videos_per_page={per_page}"

    return f"{base}/{page_number}/?videos_per_page={per_page}"


def scrape_artist(
    page: Page, artist_url: str, per_page: int = VIDEOS_PER_PAGE
) -> tuple[list[str], str | None]:
    """Scrape all video links for one artist."""
    all_links: list[str] = []

    first_html = open_page(page, get_artist_page_url(artist_url, 1, per_page))
    artist_name = extract_artist_name(first_html)
    page_count = extract_page_count(first_html, artist_url)

    print(f"Found {page_count} page(s) for artist")
    save_session_data(page)

    counter = 1

    for page_number in range(1, page_count + 1):
        print(f"\n--- Page {page_number}/{page_count} ---")

        if page_number == 1:
            page_html = first_html
        else:
            page_url = get_artist_page_url(artist_url, page_number, per_page)
            page_html = open_page(page, page_url)

        page_links = extract_video_links(page_html)

        if not page_links:
            print("No links found on this page")
            continue

        for link in page_links:
            print(f"{counter:04d}. {link}")
            all_links.append(link)
            counter += 1

    return list(dict.fromkeys(all_links)), artist_name


def extract_video_download(page: Page, video_url: str) -> tuple[str | None, str | None]:
    """Extract the best downloadable mp4 for a video."""
    raw_html = html.unescape(open_page(page, video_url))
    video_id = extract_video_id(raw_html)

    # Get the video src set by JS on the <video> element (has valid token)
    video_src = page.evaluate('() => document.querySelector("video")?.src || ""')

    if not video_src:
        page.wait_for_timeout(3000)
        video_src = page.evaluate('() => document.querySelector("video")?.src || ""')
        video_id = video_id or extract_video_id(html.unescape(page.content()))

    if video_src:
        return video_id, video_src

    # Fallback: extract from page HTML
    mp4_urls = extract_mp4_urls(raw_html)
    best_mp4 = get_best_quality_mp4(mp4_urls)
    return video_id, best_mp4


def resolve_stream_url(page: Page, mp4_url: str) -> str:
    """Resolve the final stream url."""
    response = page.request.head(mp4_url, max_redirects=0)
    location = response.headers.get("location")
    return location if location else mp4_url


def show_download_screen(page: Page, video_id: str | None) -> None:
    """Show a simple status page."""
    page.goto("about:blank")
    page.set_content(
        f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Downloading...</title>
<style>
body {{
    background: #1a0033;
    color: white;
    font-family: Arial, sans-serif;
    text-align: center;
    padding-top: 100px;
}}
</style>
</head>
<body>
    <h1>PimpBunny Downloader</h1>
    <p>Downloading video {video_id or "unknown"}...</p>
</body>
</html>"""
    )


# -----------------------------
# artist processing
# -----------------------------
def process_artist(page: Page, artist_url: str, user_agent: str) -> None:
    """Process one artist."""
    artist_slug = artist_url.rstrip("/").split("/")[-1]

    print(f"\n\n{'#' * 60}\nScraping: {artist_url}\n{'#' * 60}")

    video_links, artist_name = scrape_artist(page, artist_url)

    if artist_name == "Page Not Found":
        print(f"Skipping {artist_url} - Page Not Found")
        return

    folder_name = (artist_name or artist_slug).strip()
    artist_dir = os.path.join(ARTISTS_DIR, folder_name)
    ensure_dir(artist_dir)

    links_file = os.path.join(artist_dir, "_links.txt")
    rows: list[tuple[str, str]] = []

    print(f"\n########## Processing {folder_name} ##########")

    for index, video_url in enumerate(video_links, start=1):
        print(f"\n[{index}/{len(video_links)}] Processing: {video_url}")

        video_id, best_mp4 = extract_video_download(page, video_url)

        if not video_id:
            print("Could not find video id.")
            continue

        if not best_mp4:
            print("No valid MP4 link found for this video.")
            continue

        final_output = os.path.join(artist_dir, f"{video_id}.mp4")
        pending_output = os.path.join(PENDING_DIR, f"{video_id}.mp4")

        if os.path.exists(final_output):
            print(f"Already downloaded: {final_output}")
            continue

        print(f"Best quality MP4: {best_mp4}")

        stream_url = resolve_stream_url(page, best_mp4)
        rows.append((video_id, stream_url))

        show_download_screen(page, video_id)

        cookies = page.context.cookies()
        print("Downloading with niquests...")

        success = download_file(
            stream_url=stream_url,
            output_path=pending_output,
            user_agent=user_agent,
            cookies=cookies,
        )

        if success and os.path.exists(pending_output):
            os.replace(pending_output, final_output)
            print(f"✓ Saved: {final_output}")
        else:
            print(f"✗ Download failed for {video_id}")
            if os.path.exists(pending_output):
                try:
                    os.remove(pending_output)
                except OSError:
                    pass

    with open(links_file, "w", encoding="utf-8") as file:
        seen: dict[str, str] = dict.fromkeys(rows)
        for video_id, stream_url in seen:
            file.write(f"{video_id}\t{stream_url}\n")

    print(f"\nFinished {folder_name} — Saved {len(rows)} videos.")


# -----------------------------
# setup
# -----------------------------
def load_artist_urls(path: str) -> list[str]:
    """Load and sort artist urls."""
    urls = sorted(set(read_lines(path)), key=str.lower)
    write_lines(path, urls)
    return urls


def build_page(browser) -> Page:
    """Build a browser page."""
    return make_page(browser, COOKIE_FILE)


# -----------------------------
# main
# -----------------------------
def main() -> None:
    """Run the downloader."""
    ensure_dir(PENDING_DIR)
    clear_dir(PENDING_DIR)
    atexit.register(lambda: clear_dir(PENDING_DIR))

    if not os.path.exists(ARTIST_LIST_FILE):
        print(f"Error: {ARTIST_LIST_FILE} not found!")
        sys.exit(1)

    artist_urls = load_artist_urls(ARTIST_LIST_FILE)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True, args=["--mute-audio"])
        except Exception:
            print(
                "Failed to launch browser. Try running with:\n"
                "   xvfb-run python pimpbunny_downloader.py"
            )
            sys.exit(1)

        page = build_page(browser)
        user_agent = page.evaluate("() => navigator.userAgent")

        for artist_url in artist_urls:
            process_artist(page, artist_url, user_agent)

        print("\nAll artists processed!")
        browser.close()


if __name__ == "__main__":
    main()
