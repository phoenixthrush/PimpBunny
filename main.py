"""
PimpBunny Downloader - Combined Script
Scrapes video links from pimpbunny.com and downloads them using niquests with a tqdm progress bar.
"""

import atexit
import html
import os
import re
import shutil
import sys
import tempfile

# External HTTP client and progress bar
import niquests
from patchright.sync_api import Page, sync_playwright
from tqdm import tqdm

# ========================= CONFIG =========================
PENDING_DIR = "pending"
ARTISTS_DIR = "artists"
ARTIST_LIST_FILE = "artists.txt"
COOKIE_FILE = "cookies.txt"
USER_AGENT_FILE = "user_agent.txt"
VIDEOS_PER_PAGE = 128
# =========================================================


# -----------------------------
# Pending downloads
# -----------------------------
def ensure_pending_dir() -> None:
    os.makedirs(PENDING_DIR, exist_ok=True)


def clear_pending_dir() -> None:
    ensure_pending_dir()
    for name in os.listdir(PENDING_DIR):
        path = os.path.join(PENDING_DIR, name)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as e:
            print(f"Could not remove pending item: {path} ({e})")


# -----------------------------
# Extraction Functions
# -----------------------------
def extract_video_links(page_html: str) -> list[str]:
    pattern = r'<a[^>]+class="[^"]*ui-card-link[^"]*"[^>]+href="([^"]+)"'
    return re.findall(pattern, page_html)


def extract_video_id(page_html: str) -> str | None:
    match = re.search(r"videoId:\s*'(\d+)'", page_html)
    return match.group(1) if match else None


def extract_artist_name(page_html: str) -> str | None:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.DOTALL)
    if not match:
        return None
    return html.unescape(match.group(1)).strip()


def extract_page_count(page_html: str, artist_url: str) -> int:
    artist_base = artist_url.rstrip("/").split("/")[-1]
    pattern = rf'href="[^"]*{artist_base}/(\d+)(?:/)?(?:\?[^"]*)?"[^>]*>(\d+)</a>'
    nums = [int(num) for _, num in re.findall(pattern, page_html)]
    return max(nums) if nums else 1


def extract_mp4_links(page: Page, url: str) -> tuple[list[str], str | None]:
    page.goto(url)

    for _ in range(10):
        if "<title>Just a moment...</title>" in page.content():
            print("Cloudflare protection detected, waiting 5 seconds...")
            page.wait_for_timeout(5000)

    page.wait_for_timeout(500)
    raw_html = html.unescape(page.content())

    video_id = extract_video_id(raw_html)
    urls = re.findall(r"https?://[^\s'\"]+\.mp4[^\s'\"]*", raw_html)

    unique_by_file: dict[str, str] = {}

    for mp4_url in urls:
        mp4_url = mp4_url.replace("function/0/", "")
        if "_preview" in mp4_url or ".jpg" in mp4_url or "download=true" not in mp4_url:
            continue

        match = re.search(r"/([^/?]+\.mp4)", mp4_url)
        if match:
            file_name = match.group(1)
            unique_by_file[file_name] = mp4_url

    return list(unique_by_file.values()), video_id


def get_best_quality_mp4(urls: list[str]) -> str | None:
    best_url = None
    best_quality = -1

    for url in urls:
        match = re.search(r"_(\d{3,4})p\.mp4", url)
        quality = int(match.group(1)) if match else 0
        if quality > best_quality:
            best_quality = quality
            best_url = url

    return best_url


# -----------------------------
# Cookie Handling
# -----------------------------
def save_cookies_netscape(cookies: list[dict], path: str) -> None:
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in cookies:
        domain = cookie.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path_value = cookie.get("path", "/")
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"
        expires = (
            int(cookie.get("expires", 0))
            if cookie.get("expires") not in (-1, None)
            else 0
        )
        name = cookie.get("name", "")
        value = cookie.get("value", "")

        lines.append(
            "\t".join(
                [
                    domain,
                    include_subdomains,
                    path_value,
                    secure,
                    str(expires),
                    name,
                    value,
                ]
            )
        )

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_netscape_cookies(path: str) -> list[dict]:
    cookies: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
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
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7 and parts[5] == "cf_clearance":
                    return parts[6]
    except FileNotFoundError:
        pass
    return None


# -----------------------------
# Build curl command (kept for compatibility but not used)
# -----------------------------
def build_curl_command(
    output_path: str, stream_url: str, user_agent: str, cf_clearance: str | None = None
) -> list[str]:
    cmd = [
        "curl",
        stream_url,
        "-H",
        f"User-Agent: {user_agent}",
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H",
        "Accept-Language: en-US,en;q=0.9",
        "-H",
        "Accept-Encoding: gzip, deflate, br, zstd",
        "-H",
        "DNT: 1",
        "-H",
        "Sec-GPC: 1",
        "-H",
        "Connection: keep-alive",
        "-H",
        "Upgrade-Insecure-Requests: 1",
        "-H",
        "Sec-Fetch-Dest: document",
        "-H",
        "Sec-Fetch-Mode: navigate",
        "-H",
        "Sec-Fetch-Site: none",
        "-H",
        "Sec-Fetch-User: ?1",
        "-H",
        "Priority: u=0, i",
        "-H",
        "TE: trailers",
        "-o",
        output_path,
        "--fail",
        "--silent",
        "--show-error",
    ]

    if cf_clearance:
        cmd.insert(10, "-H")
        cmd.insert(11, f"Cookie: cf_clearance={cf_clearance}")

    return cmd


# -----------------------------
# niquests download helper with tqdm
# -----------------------------
def download_with_niquests(
    stream_url: str,
    pending_output: str,
    user_agent: str,
    cf_clearance: str | None = None,
    timeout: int = 60,
) -> bool:
    """
    Stream-download stream_url to a temporary file and move to pending_output on success.
    Shows a tqdm progress bar using Content-Length when available.
    Returns True on success, False on failure.
    """
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

    if cf_clearance:
        headers["Cookie"] = f"cf_clearance={cf_clearance}"

    temp_dir = os.path.dirname(os.path.abspath(pending_output)) or "."
    fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(pending_output) + ".", suffix=".temp", dir=temp_dir
    )
    os.close(fd)

    try:
        with niquests.get(
            stream_url, headers=headers, stream=True, timeout=timeout
        ) as resp:
            try:
                resp.raise_for_status()
            except Exception as e:
                print(f"HTTP error while downloading {stream_url}: {e}")
                return False

            # Try to get total size for tqdm
            total = None
            content_length = resp.headers.get("Content-Length") or resp.headers.get(
                "content-length"
            )
            if content_length and content_length.isdigit():
                total = int(content_length)

            chunk_size = 8192
            with open(temp_path, "wb") as out_f:
                if total:
                    with tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(pending_output),
                        leave=True,
                    ) as pbar:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                out_f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    # Unknown total size: use indeterminate progress bar
                    with tqdm(
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=os.path.basename(pending_output),
                        leave=True,
                    ) as pbar:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                out_f.write(chunk)
                                pbar.update(len(chunk))

        os.replace(temp_path, pending_output)
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
# Scraping
# -----------------------------
def scrape_artist(
    page: Page, artist_url: str, per_page: int = VIDEOS_PER_PAGE
) -> tuple[list[str], str | None]:
    all_links: list[str] = []

    first_url = f"{artist_url.rstrip('/')}/?videos_per_page={per_page}"
    page.goto(first_url)

    for _ in range(10):
        if "<title>Just a moment...</title>" in page.content():
            print("Cloudflare protection detected, waiting 5 seconds...")
            page.wait_for_timeout(5000)

    first_html = page.content()
    artist_name = extract_artist_name(first_html)
    page_count = extract_page_count(first_html, artist_url)

    print(f"Found {page_count} page(s) for artist")

    # Save user agent and cookies
    user_agent = page.evaluate("() => navigator.userAgent")
    with open(USER_AGENT_FILE, "w", encoding="utf-8") as f:
        f.write(user_agent)
    print(f"Saved user agent to {USER_AGENT_FILE}")

    cookies = page.context.cookies()
    save_cookies_netscape(cookies, COOKIE_FILE)
    print(f"Saved cookies to {COOKIE_FILE}")

    counter = 1
    for page_num in range(1, page_count + 1):
        print(f"\n--- Page {page_num}/{page_count} ---")

        if page_num == 1:
            page_html = first_html
        else:
            page_url = (
                f"{artist_url.rstrip('/')}/{page_num}/?videos_per_page={per_page}"
            )
            page.goto(page_url)
            page_html = page.content()

            for _ in range(10):
                if "<title>Just a moment...</title>" in page_html:
                    print("Cloudflare protection detected, waiting 5 seconds...")
                    page.wait_for_timeout(5000)

        page_links = extract_video_links(page_html)
        if not page_links:
            print("No links found on this page")
            continue

        for href in page_links:
            print(f"{counter:04d}. {href}")
            all_links.append(href)
            counter += 1

    return all_links, artist_name


# -----------------------------
# Main Function
# -----------------------------
def main() -> None:
    ensure_pending_dir()
    clear_pending_dir()
    atexit.register(clear_pending_dir)

    if not os.path.exists(ARTIST_LIST_FILE):
        print(f"Error: {ARTIST_LIST_FILE} not found!")
        sys.exit(1)

    with open(ARTIST_LIST_FILE, "r", encoding="utf-8") as f:
        artist_urls = sorted(
            {
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            },
            key=str.lower,
        )

    with open(ARTIST_LIST_FILE, "w", encoding="utf-8") as f:
        for url in artist_urls:
            f.write(f"{url}\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--mute-audio"])
        except Exception:
            print(
                "Failed to launch browser. Try running with:\n   xvfb-run python pimpbunny_downloader.py"
            )
            sys.exit(1)

        # Load cookies if available
        if os.path.exists(COOKIE_FILE):
            context = browser.new_context()
            cookies = load_netscape_cookies(COOKIE_FILE)
            context.add_cookies(cookies)
            page = context.new_page()
            print("Loaded saved cookies from previous session")
        else:
            page = browser.new_page()
            print("No cookies.txt found - starting fresh")

        user_agent = page.evaluate("() => navigator.userAgent")

        for artist_url in artist_urls:
            artist_slug = artist_url.rstrip("/").split("/")[-1]
            print(f"\n\n{'#' * 60}\nScraping: {artist_url}\n{'#' * 60}")

            video_links, artist_name = scrape_artist(page, artist_url)
            video_links = list(dict.fromkeys(video_links))

            if artist_name == "Page Not Found":
                print(f"Skipping {artist_url} - Page Not Found")
                continue

            output_dir = (artist_name or artist_slug).strip()
            artist_folder = os.path.join(ARTISTS_DIR, output_dir)
            os.makedirs(artist_folder, exist_ok=True)

            links_file = os.path.join(artist_folder, "_links.txt")

            print(f"\n########## Processing {output_dir} ##########")

            rows: list[tuple[str, str]] = []

            for index, link in enumerate(video_links, start=1):
                print(f"\n[{index}/{len(video_links)}] Processing: {link}")

                mp4_urls, video_id = extract_mp4_links(page, link)
                best_mp4 = get_best_quality_mp4(mp4_urls)

                final_output = os.path.join(artist_folder, f"{video_id}.mp4")
                pending_output = os.path.join(PENDING_DIR, f"{video_id}.mp4")

                if os.path.exists(final_output):
                    print(f"Already downloaded: {final_output}")
                    continue

                if not best_mp4:
                    print("No valid MP4 link found for this video.")
                    continue

                print(f"Best quality MP4: {best_mp4}")

                # Stream setup
                stream_response = page.goto(
                    best_mp4.replace("download=true", "download=false")
                )
                for _ in range(10):
                    if "<title>Just a moment...</title>" in page.content():
                        print("Cloudflare detected during streaming, waiting...")
                        page.wait_for_timeout(5000)

                page.goto("about:blank")
                page.set_content(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Downloading...</title>
<style>body{{background:#1a0033;color:white;font-family:Arial;text-align:center;padding-top:100px;}}</style>
</head><body>
<h1>PimpBunny Downloader</h1>
<p>Downloading video {video_id}...</p>
</body></html>""")

                stream_url = stream_response.url if stream_response else best_mp4
                rows.append((video_id or "", stream_url))

                cf_clearance = get_cf_clearance()

                print(
                    "Downloading with niquests..."
                    + (" (with cf_clearance)" if cf_clearance else " (no cf_clearance)")
                )

                success = download_with_niquests(
                    stream_url=stream_url,
                    pending_output=pending_output,
                    user_agent=user_agent,
                    cf_clearance=cf_clearance,
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

            # Save links file
            with open(links_file, "w", encoding="utf-8") as f:
                for vid, url in dict.fromkeys(rows):
                    f.write(f"{vid}\t{url}\n")

            print(f"\nFinished {output_dir} — Saved {len(rows)} videos.")

        print("\nAll artists processed!")
        browser.close()


if __name__ == "__main__":
    main()
