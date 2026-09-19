from pathlib import Path
import hashlib

import requests


BASE_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = BASE_DIR / "data" / "raw"

OUTPUT_FILE = (
    RAW_DIR
    / "mospi_flash_report_march_2026.pdf"
)


OFFICIAL_URL = (
    "https://ipm.mospi.gov.in/"
    "Content/PDF/FlashReport_March_2026.pdf"
)


def calculate_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(
            lambda: file.read(8192),
            b"",
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def download_file():
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n==============================")
    print("LIVA OFFICIAL DATA DOWNLOADER")
    print("==============================")

    print("\nSource:")
    print("MoSPI - IPMD / PAIMANA")

    print("\nOfficial URL:")
    print(OFFICIAL_URL)

    response = requests.get(
        OFFICIAL_URL,
        timeout=60,
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "content-type",
        "",
    )

    if "pdf" not in content_type.lower():
        print(
            "\nWarning: server content type:",
            content_type,
        )

    OUTPUT_FILE.write_bytes(
        response.content
    )

    file_size = (
        OUTPUT_FILE.stat().st_size
        / 1024
        / 1024
    )

    checksum = calculate_sha256(
        OUTPUT_FILE
    )

    print("\nDownload successful.")

    print(
        "Saved:",
        OUTPUT_FILE,
    )

    print(
        f"Size: {file_size:.2f} MB"
    )

    print(
        "SHA256:",
        checksum,
    )


if __name__ == "__main__":
    download_file()