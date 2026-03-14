import subprocess

# -----------------------------
# Files
# -----------------------------
COOKIE_FILE = "cookies.txt"
USER_AGENT_FILE = "user_agent.txt"
VIDEO_FILE = "hannah-owo-exclusive-leaks.txt"


# -----------------------------
# Read cookie
# -----------------------------
def get_cf_clearance(path: str = COOKIE_FILE) -> str | None:
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
# Read text
# -----------------------------
def read_text(path: str) -> str:
    """Read a text file."""
    with open(path, "r", encoding="utf-8") as file:
        return file.read().strip()


# -----------------------------
# Read video rows
# -----------------------------
def read_video_rows(path: str) -> list[tuple[str, str]]:
    """Read video rows from a file."""
    rows: list[tuple[str, str]] = []

    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
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


# -----------------------------
# Build command
# -----------------------------
def build_curl_command(
    video_id: str,
    stream_url: str,
    user_agent: str,
    cf_clearance: str,
) -> list[str]:
    """Build the curl command."""
    return [
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


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    """Download videos from saved rows."""
    cf_clearance = get_cf_clearance()
    if not cf_clearance:
        raise RuntimeError("cf_clearance cookie not found")

    user_agent = read_text(USER_AGENT_FILE)
    if not user_agent:
        raise RuntimeError("user_agent.txt is empty")

    rows = read_video_rows(VIDEO_FILE)
    total = len(rows)

    for index, (video_id, stream_url) in enumerate(rows, start=1):
        print(f"[{index}/{total}] Downloading {video_id}.mp4")

        command = build_curl_command(
            video_id=video_id,
            stream_url=stream_url,
            user_agent=user_agent,
            cf_clearance=cf_clearance,
        )

        _result = subprocess.run(command, check=False)

        # if _result.returncode == 0:
        #    print(f"[{index}/{total}] Done {video_id}.mp4")
        # else:
        #    print(f"[{index}/{total}] Failed {video_id}.mp4")


if __name__ == "__main__":
    main()
