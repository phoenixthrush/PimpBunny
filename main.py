"""
Get video links from pimpbunny.com using regex.
Sequential numbering across pages
"""

import html
import os
import re

from patchright.sync_api import Page, sync_playwright


# -----------------------------
# Video links
# -----------------------------
def extract_video_links(page_html: str) -> list[str]:
    """Get all video links from a page."""
    pattern = r'<a[^>]+class="[^"]*ui-card-link[^"]*"[^>]+href="([^"]+)"'
    return re.findall(pattern, page_html)


def extract_video_id(page_html: str) -> str | None:
    """Get the video id from pageContext."""
    match = re.search(r"videoId:\s*'(\d+)'", page_html)
    return match.group(1) if match else None


def extract_artist_name(page_html: str) -> str | None:
    """Get the artist name from the page heading."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.DOTALL)
    if not match:
        return None

    return html.unescape(match.group(1)).strip()


# -----------------------------
# Pagination count
# -----------------------------
def extract_page_count(page_html: str, artist_url: str) -> int:
    """Get max page number from pagination."""
    artist_base = artist_url.rstrip("/").split("/")[-1]
    pattern = rf'href="[^"]*{artist_base}/(\d+)(?:/)?(?:\?[^"]*)?"[^>]*>(\d+)</a>'
    nums = [int(num) for _, num in re.findall(pattern, page_html)]
    return max(nums) if nums else 1


# -----------------------------
# MP4 link extraction
# -----------------------------
def extract_mp4_links(page: Page, url: str) -> tuple[list[str], str | None]:
    """Get unique downloadable .mp4 URLs and video id from the page."""
    page.goto(url)

    raw_html = html.unescape(page.content())
    video_id = extract_video_id(raw_html)
    urls = re.findall(r"https?://[^\s'\"]+\.mp4[^\s'\"]*", raw_html)

    unique_by_file: dict[str, str] = {}

    for mp4_url in urls:
        mp4_url = mp4_url.replace("function/0/", "")

        if "_preview" in mp4_url:
            continue

        if ".jpg" in mp4_url:
            continue

        if "download=true" not in mp4_url:
            continue

        match = re.search(r"/([^/?]+\.mp4)", mp4_url)
        if not match:
            continue

        file_name = match.group(1)
        unique_by_file[file_name] = mp4_url

    return list(unique_by_file.values()), video_id


def get_best_quality_mp4(urls: list[str]) -> str | None:
    """Return .mp4 URL with highest quality number."""
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
# Cookie saving
# -----------------------------
def save_cookies_netscape(cookies: list[dict], path: str) -> None:
    """Save cookies in Netscape format."""
    lines = ["# Netscape HTTP Cookie File"]

    for cookie in cookies:
        domain = cookie.get("domain", "")
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path_value = cookie.get("path", "/")
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"

        expires = cookie.get("expires", 0)
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
                    path_value,
                    secure,
                    str(expires),
                    name,
                    value,
                ]
            )
        )

    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
        file.write("\n")


# -----------------------------
# Scraping
# -----------------------------
def scrape_artist(
    page: Page, artist_url: str, per_page: int = 128
) -> tuple[list[str], str | None]:
    """Scrape all video links for one artist."""
    all_links: list[str] = []

    first_url = f"{artist_url.rstrip('/')}/?videos_per_page={per_page}"
    page.goto(first_url)

    first_html = page.content()
    artist_name = extract_artist_name(first_html)
    page_count = extract_page_count(first_html, artist_url)

    print(f"Found {page_count} page(s)")

    user_agent = page.evaluate("() => navigator.userAgent")

    with open("user_agent.txt", "w", encoding="utf-8") as ua_file:
        ua_file.write(user_agent)
        print("Saved user agent to user_agent.txt")

    cookies = page.context.cookies()
    save_cookies_netscape(cookies, "cookies.txt")
    print("Saved cookies to cookies.txt")

    counter = 1

    for page_num in range(1, page_count + 1):
        print(f"\n--- Page {page_num} ---")

        if page_num == 1:
            page_html = first_html
        else:
            page_url = (
                f"{artist_url.rstrip('/')}/{page_num}/?videos_per_page={per_page}"
            )
            page.goto(page_url)
            page_html = page.content()

        page_links = extract_video_links(page_html)

        if not page_links:
            print("No links found")
            continue

        for href in page_links:
            print(f"{counter:04d}. {href}")
            all_links.append(href)
            counter += 1

    return all_links, artist_name


def load_netscape_cookies(path: str) -> list[dict]:
    """Load cookies from a Netscape cookie file."""
    cookies: list[dict] = []

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain, _subdomains, cookie_path, secure, expires, name, value = parts[:7]

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


# --------- Main ---------
if __name__ == "__main__":
    artist_list_file = "artists.txt"

    with open(artist_list_file, "r", encoding="utf-8") as file:
        artist_urls = sorted(
            {line.strip() for line in file if line.strip()},
            key=str.lower,
        )

    with open(artist_list_file, "w", encoding="utf-8") as file:
        for artist_url in artist_urls:
            file.write(f"{artist_url}\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, args=["--mute-audio"])
        except Exception:
            print(
                "Loading cookies that manually passed the captcha does work for bypassing Cloudflare.\n"
                "It just still does not work in normal headless mode, even if no captcha is shown.\n"
                "It does work headless when using a virtual X display like xvfb-run :)\n\n"
                "Just install Xvfb and run:\n"
                "xvfb-run python main.py"
            )
            exit(1)

        if os.path.exists("cookies.txt"):
            context = browser.new_context()
            cookies = load_netscape_cookies("cookies.txt")
            context.add_cookies(cookies)

            page = context.new_page()
        else:
            page = browser.new_page()

        for artist_url in artist_urls:
            artist_slug = artist_url.rstrip("/").split("/")[-1]

            video_links, artist_name = scrape_artist(page, artist_url)
            video_links = list(dict.fromkeys(video_links))

            print(artist_name)
            if artist_name == "Page Not Found":
                print(f"Skipping {artist_url} - Page Not Found")
                continue

            output_dir = (artist_name or artist_slug).strip()
            output_file = f"artists/{output_dir}/_links.txt"

            os.makedirs(f"artists/{output_dir}", exist_ok=True)

            print(f"\n########## {output_dir} ##########")

            rows: list[tuple[str, str]] = []

            for index, link in enumerate(video_links, start=1):
                mp4_urls, video_id = extract_mp4_links(page, link)
                best_mp4 = get_best_quality_mp4(mp4_urls)

                print(f"\n=== [{index}/{len(video_links)}] Video page: {link} ===")
                print(f"Video ID: {video_id}")
                print(f"MP4 URLs: {mp4_urls}")
                print(f"Best MP4: {best_mp4}")

                if best_mp4:
                    stream_response = page.goto(
                        best_mp4.replace("download=true", "download=false")
                    )

                    stream_url = stream_response.url if stream_response else best_mp4

                    rows.append((video_id or "", stream_url))

                    print("Stream URL:", stream_url)

                print("-----------------------------")

            rows = list(dict.fromkeys(rows))

            with open(output_file, "w", encoding="utf-8") as file:
                for video_id, stream_url in rows:
                    file.write(f"{video_id}\t{stream_url}\n")

            print(f"\nSaved {len(rows)} rows to {output_file}")

        # input("\nPress Enter to close the browser...")
        browser.close()
