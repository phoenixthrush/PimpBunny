import os
import subprocess

# -----------------------------
# Files
# -----------------------------
ARTISTS_DIR = "artists"
COOKIE_FILE = "cookies.txt"
USER_AGENT_FILE = "user_agent.txt"


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
                print(f"Skipping bad line {line_number} in {path}: {line}")
                continue

            video_id, stream_url = parts[0].strip(), parts[1].strip()

            if not video_id or not stream_url:
                print(f"Skipping incomplete line {line_number} in {path}: {line}")
                continue

            rows.append((video_id, stream_url))

    return rows


# -----------------------------
# Find link files
# -----------------------------
def find_link_files(root_dir: str) -> list[str]:
    """Find all _links.txt files under the artists folder."""
    link_files: list[str] = []

    for current_root, _dirs, files in os.walk(root_dir):
        for name in files:
            if name == "_links.txt":
                link_files.append(os.path.join(current_root, name))

    return sorted(link_files)


# -----------------------------
# Build command
# -----------------------------
def build_curl_command(
    output_path: str,
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
        output_path,
    ]


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    """Download videos from artist link files."""
    cf_clearance = get_cf_clearance()
    if not cf_clearance:
        raise RuntimeError("cf_clearance cookie not found")

    user_agent = read_text(USER_AGENT_FILE)
    if not user_agent:
        raise RuntimeError("user_agent.txt is empty")

    link_files = find_link_files(ARTISTS_DIR)
    if not link_files:
        raise RuntimeError("No _links.txt files found")

    for link_file in link_files:
        artist_dir = os.path.dirname(link_file)
        artist_name = os.path.basename(artist_dir)
        rows = read_video_rows(link_file)
        total = len(rows)

        print(f"\n########## {artist_name} ##########")

        for index, (video_id, stream_url) in enumerate(rows, start=1):
            output_path = os.path.join(artist_dir, f"{video_id}.mp4")

            if os.path.exists(output_path):
                print(f"[{index}/{total}] Skipping {output_path}")
                continue

            print(f"[{index}/{total}] Downloading {output_path}")

            command = build_curl_command(
                output_path=output_path,
                stream_url=stream_url,
                user_agent=user_agent,
                cf_clearance=cf_clearance,
            )

            subprocess.run(command, check=False)


if __name__ == "__main__":
    main()
