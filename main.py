"""
Get video links from pimpbunny.com using regex.
Sequential numbering across pages
"""

import html
import re

from patchright.sync_api import Page, sync_playwright


# -----------------------------
# Video links
# -----------------------------
def extract_video_links(html: str) -> list[str]:
    """Get all video links from a page."""
    pattern = r'<a[^>]+class="[^"]*ui-card-link[^"]*"[^>]+href="([^"]+)"'
    return re.findall(pattern, html)


# -----------------------------
# Pagination count
# -----------------------------
def extract_page_count(html: str, artist_url: str) -> int:
    """Get max page number from pagination."""
    artist_base = artist_url.rstrip("/").split("/")[-1]
    pattern = rf'href="[^"]*{artist_base}/(\d+)(?:/)?(?:\?[^"]*)?"[^>]*>(\d+)</a>'
    nums = [int(num) for _, num in re.findall(pattern, html)]
    return max(nums) if nums else 1


# -----------------------------
# MP4 link extraction
# -----------------------------
def extract_mp4_links(page: Page, url: str, delay_ms: int = 1000) -> list[str]:
    """Get unique downloadable .mp4 URLs from the page."""
    page.goto(url)
    page.wait_for_timeout(delay_ms)

    raw_html = html.unescape(page.content())
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

    return list(unique_by_file.values())


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
def scrape_artist(page: Page, artist_url: str, per_page: int = 128) -> list[str]:
    """Scrape all video links for one artist."""
    all_links: list[str] = []

    first_url = f"{artist_url.rstrip('/')}/?videos_per_page={per_page}"
    page.goto(first_url)
    page.wait_for_timeout(10000)

    first_html = page.content()
    page_count = extract_page_count(first_html, artist_url)

    print(f"Found {page_count} page(s)")

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
            page.wait_for_timeout(1000)
            page_html = page.content()

        page_links = extract_video_links(page_html)

        if not page_links:
            print("No links found")
            continue

        for href in page_links:
            print(f"{counter:04d}. {href}")
            all_links.append(href)
            counter += 1

    return all_links


# --------- Main ---------
if __name__ == "__main__":
    artist_url = "https://pimpbunny.com/onlyfans-models/ruth-lee-leaks/"
    artist_slug = artist_url.rstrip("/").split("/")[-1]
    output_file = f"{artist_slug}.txt"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        video_links = list(dict.fromkeys(scrape_artist(page, artist_url)))
        best_links: list[str] = []

        for link in video_links:
            mp4_urls = extract_mp4_links(page, link, delay_ms=1000)
            best_mp4 = get_best_quality_mp4(mp4_urls)

            print(
                f"\n=== [{video_links.index(link) + 1}/{len(video_links)}] Video page: {link} ==="
            )
            print(f"MP4 URLs: {mp4_urls}")
            print(f"Best MP4: {best_mp4}")

            if best_mp4:
                stream_url = page.goto(
                    best_mp4.replace("download=true", "download=false")
                )

                page.wait_for_timeout(1000)
                best_links.append(stream_url.url if stream_url else best_mp4)

                print("Stream URL:", stream_url.url if stream_url else "No stream URL")

            print("-----------------------------")

        best_links = list(dict.fromkeys(best_links))

        with open(output_file, "w", encoding="utf-8") as file:
            file.write("\n".join(best_links))
            file.write("\n")

        print(f"\nSaved {len(best_links)} links to {output_file}")

        input("\nPress Enter to close the browser...")
        browser.close()
