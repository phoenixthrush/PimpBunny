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


# -----------------------------
# Read video rows
# -----------------------------
def read_video_rows(path: str) -> list[tuple[str, str]]:
    """Read video rows from a file."""
    rows: list[tuple[str, str]] = []

    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.rstrip("\n")

            if not line.strip():
                continue

            parts = line.split(None, 1)

            if len(parts) != 2:
                print(f"Skipping bad line {line_number}: {line}")
                continue

            video_id, stream_url = parts[0].strip(), parts[1].strip()

            if not video_id or not stream_url:
                print(f"Skipping incomplete line {line_number}: {line}")
                continue

            rows.append((video_id, stream_url))

    return rows


cf_clearance = get_cf_clearance()
rows = read_video_rows("hannah-owo-exclusive-leaks.txt")

# Note: Cookie is not enough as its hashed with the User-Agent so the same User-Agent must be the same when downloading
for video_id, stream_url in rows:
    command = [
        "curl",
        stream_url,
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
        f"{video_id}.mp4",
    ]

    subprocess.run(command, check=False)

    print(f"Ran: {' '.join(subprocess.list2cmdline([arg]) for arg in command)}")
