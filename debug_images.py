"""
Diagnostic script - Phase 1 evidence gathering.
Tests 3 root cause candidates without running full Docling conversion.
"""
import re
import mimetypes
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests

TARGET_URL = "https://github.com/donnemartin/system-design-primer"

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
})

# ===== CHECK 1: Fetch raw HTML, extract img tags to see what URLs look like =====
print("=" * 60)
print("CHECK 1: Raw HTML image URLs from GitHub page")
print("=" * 60)
res = session.get(TARGET_URL, timeout=15)
print(f"Status: {res.status_code}, Content-Type: {res.headers.get('Content-Type','')}")

# Find img src in raw HTML
html_imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', res.text)
print(f"Found {len(html_imgs)} <img> tags in HTML")
for url in html_imgs[:5]:
    print(f"  src: {url[:100]}")

# Find markdown image refs in raw HTML (README content rendered)
md_imgs = re.findall(r'!\[.*?\]\((.*?)\)', res.text)
print(f"\nFound {len(md_imgs)} markdown-style image refs in HTML")
for url in md_imgs[:5]:
    print(f"  url: {url[:100]}")

# ===== CHECK 2: Try downloading one camo/githubusercontent image =====
print("\n" + "=" * 60)
print("CHECK 2: Test download of a camo.githubusercontent.com image")
print("=" * 60)
camo_imgs = [u for u in html_imgs if "camo.githubusercontent" in u or "raw.githubusercontent" in u]
if camo_imgs:
    test_url = camo_imgs[0]
    print(f"Testing: {test_url[:80]}...")
    try:
        r = session.get(test_url, timeout=10)
        print(f"  Status: {r.status_code}")
        print(f"  Content-Type: {r.headers.get('Content-Type','')}")
        print(f"  Content-Length: {len(r.content)} bytes")
        print(f"  First bytes: {r.content[:20]}")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("  No camo/raw githubusercontent URLs found in HTML img tags")

# ===== CHECK 3: Check if urljoin works correctly for relative URLs =====
print("\n" + "=" * 60)
print("CHECK 3: urljoin behavior with relative image paths")
print("=" * 60)
test_relatives = [
    "images/jj3A5N8.png",
    "./images/jj3A5N8.png",
    "/donnemartin/system-design-primer/raw/main/images/jj3A5N8.png",
    "https://camo.githubusercontent.com/abc123",
]
for rel in test_relatives:
    joined = urljoin(TARGET_URL, rel)
    print(f"  urljoin('{rel[:40]}') -> '{joined[:80]}'")

print("\n[DONE] Diagnostics complete.")
