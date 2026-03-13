import subprocess


# -----------------------------
# Read cookie
# -----------------------------
def get_cf_clearance(path: str = "cookies.txt") -> str | None:
    """Get the cf_clearance cookie value."""
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] == "cf_clearance":
                return parts[6]

    return None


cf_clearance = get_cf_clearance()

with open("milamondell.txt", "r", encoding="utf-8") as file:
    video_links = [line.strip() for line in file if line.strip()]

for video_link in video_links:
    subprocess.run(
        [
            "curl",
            video_link,
            "-H",
            "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) Gecko/20100101 Firefox/148.0",
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
            f"Cookie: cf_clearance={cf_clearance}",
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
            "ballsack.mp4",
        ]
    )
