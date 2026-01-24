
"""
Download GitHub Archive data for June 1 - July 1, 2025.
"""

import urllib.request
from pathlib import Path
from datetime import datetime, timedelta


def download_gharchive_range(start_date, end_date, output_dir="data"):
    """
    Download GH Archive data for date range.

    Args:
        start_date: Start date (datetime object)
        end_date: End date (datetime object)
        output_dir: Directory to save files
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    print("="*70)
    print("DOWNLOADING GITHUB ARCHIVE DATA")
    print("="*70)
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Output directory: {output_path.absolute()}")
    print()

    total_files = 0
    downloaded = 0
    skipped = 0
    errors = 0

    current_date = start_date
    while current_date <= end_date:
        for hour in range(24):
            filename = f"{current_date.strftime('%Y-%m-%d')}-{hour}.json.gz"
            url = f"https://data.gharchive.org/{filename}"
            output_file = output_path / filename

            total_files += 1

            if output_file.exists():
                print(f"✓ {filename} (exists)")
                skipped += 1
                continue

            try:
                print(f"Downloading {filename}...", end="", flush=True)
                urllib.request.urlretrieve(url, output_file)
                file_size = output_file.stat().st_size / (1024 * 1024)  # MB
                print(f" ✓ ({file_size:.1f} MB)")
                downloaded += 1
            except Exception as e:
                print(f" ✗ Error: {e}")
                errors += 1

        current_date += timedelta(days=1)

    print()
    print("="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    print(f"Total files: {total_files}")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Errors: {errors}")
    print("="*70)
    print()

def main():
    """Download June 1 - July 1, 2025 data."""
    start = datetime(2025, 6, 1)
    end = datetime(2025, 7, 1)

    download_gharchive_range(start, end)

    print("✓ Download complete!")
    print("Run extract_behavioral_priors.py next.")
    print()


if __name__ == "__main__":
    main()
