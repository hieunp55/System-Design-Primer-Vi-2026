import base64
import mimetypes
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from docling.document_converter import DocumentConverter

# ==========================================
# 1. CẤU HÌNH INPUT / OUTPUT
# ==========================================
TARGET_URL = "https://github.com/donnemartin/system-design-primer"  # URL trang web cần convert
OUTPUT_DIR = Path("./output")
IMAGES_DIR = OUTPUT_DIR / "images"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. PARSE CẤU TRÚC QUA DOCLING
# ==========================================
print(f"[*] Parsing DOM via Docling: {TARGET_URL}")
converter = DocumentConverter()
result = converter.convert(TARGET_URL)
raw_md = result.document.export_to_markdown()

# Quét cú pháp ảnh Markdown: ![alt](url)
img_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')
matches = img_pattern.findall(raw_md)
print(f"[*] Docling found {len(matches)} image references in Markdown.")

# ==========================================
# 2b. FALLBACK: Nếu Docling không tìm được ảnh,
#     parse trực tiếp từ HTML <img src> tags
# ==========================================
if len(matches) == 0:
    print("[*] Docling found 0 images — falling back to HTML <img> scraping.")
    session_html = requests.Session()
    session_html.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })
    html_res = session_html.get(TARGET_URL, timeout=15)
    # Extract all <img src="..."> from HTML
    html_img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_res.text)
    # Extract alt text too (optional, best effort)
    html_img_tuples = re.findall(r'<img[^>]+alt=["\']([^"\']*)["\'][^>]*src=["\']([^"\']+)["\']', html_res.text)
    alt_map = {src: alt for alt, src in html_img_tuples}

    # Build fake_matches list like Docling would produce
    # Only keep image-like URLs (skip icons, avatars, etc.)
    image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')
    filtered_srcs = [
        src for src in html_img_srcs
        if any(src.lower().split('?')[0].endswith(ext) for ext in image_extensions)
    ]
    matches = [(alt_map.get(src, f"image_{i+1}"), src) for i, src in enumerate(filtered_srcs)]

    # Inject placeholder tags into raw_md so replacement loop works
    # We'll append them at the end — they'll be stripped for embedded_md
    placeholders = "\n".join(f"![{alt}]({src})" for alt, src in matches)
    raw_md_with_placeholders = raw_md + "\n\n<!-- IMAGES -->\n" + placeholders

    print(f"[*] HTML fallback found {len(matches)} image references.")
    using_fallback = True
else:
    raw_md_with_placeholders = raw_md
    using_fallback = False

# ==========================================
# 3. TẢI VÀ CHUYỂN ĐỔI ẢNH (CACHED DOWNLOAD)
# ==========================================
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
})

# Cache lưu trữ dữ liệu đã tải: {raw_url: (local_filename, data_uri)}
url_cache = {}
img_counter = 1

def resolve_image_url(base_url: str, raw_src: str) -> str:
    """
    Resolve image URL:
    - Absolute URL: return as-is
    - github.com/.../raw/...: convert to raw.githubusercontent.com (camo bị 403)
    - Relative path: urljoin với base_url gốc (https://github.com)
    """
    if raw_src.startswith("data:"):
        return raw_src  # already base64

    # Relative path → join with github.com root (not the full page URL)
    if raw_src.startswith("/"):
        full_url = "https://github.com" + raw_src
    elif raw_src.startswith("http://") or raw_src.startswith("https://"):
        full_url = raw_src
    else:
        full_url = urljoin(base_url, raw_src)

    # Convert github.com/.../raw/... → raw.githubusercontent.com/...
    # e.g. https://github.com/user/repo/raw/master/images/x.png
    #   → https://raw.githubusercontent.com/user/repo/master/images/x.png
    if "github.com" in full_url and "/raw/" in full_url:
        full_url = (
            full_url
            .replace("https://github.com/", "https://raw.githubusercontent.com/")
            .replace("/raw/", "/")
        )

    return full_url


for alt, raw_url in matches:
    clean_url = raw_url.strip()

    # Bỏ qua nếu vốn dĩ đã là Base64
    if clean_url.startswith("data:"):
        continue

    if clean_url not in url_cache:
        full_url = resolve_image_url(TARGET_URL, clean_url)
        try:
            res = session.get(full_url, timeout=15)
            if res.status_code == 200:
                # 1. Xác định MIME type & Extension
                content_type = res.headers.get("Content-Type", "").split(";")[0].strip()
                if not content_type or not content_type.startswith("image/"):
                    content_type = mimetypes.guess_type(full_url)[0] or "image/png"

                parsed_path = urlparse(full_url).path
                ext = Path(parsed_path).suffix.lower()
                if ext not in [".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"]:
                    ext = mimetypes.guess_extension(content_type) or ".png"

                # 2. Lưu file binary ra thư mục images/
                filename = f"img_{img_counter:03d}{ext}"
                local_path = IMAGES_DIR / filename
                with open(local_path, "wb") as f:
                    f.write(res.content)

                # 3. Tạo Base64 Data URI
                b64_data = base64.b64encode(res.content).decode("utf-8")
                data_uri = f"data:{content_type};base64,{b64_data}"

                url_cache[clean_url] = (filename, data_uri)
                print(f" [+] Downloaded: {filename} <- {full_url[:70]}...")
                img_counter += 1
            else:
                print(f" [-] HTTP {res.status_code}: {full_url}")
                url_cache[clean_url] = None
        except Exception as e:
            print(f" [!] Fetch error {full_url}: {e}")
            url_cache[clean_url] = None

# ==========================================
# 4. TẠO 2 NỘI DUNG MARKDOWN
# ==========================================
if using_fallback:
    # Fallback mode: ảnh không có trong Docling MD → tạo gallery section
    embedded_lines = [raw_md, "\n\n## Images\n"]
    referenced_lines = [raw_md, "\n\n## Images\n"]

    for alt, raw_url in matches:
        clean_url = raw_url.strip()
        cache_item = url_cache.get(clean_url)
        if cache_item:
            filename, data_uri = cache_item
            embedded_lines.append(f"\n![{alt}]({data_uri})\n")
            referenced_lines.append(f"\n![{alt}](./images/{filename})\n")
        # else: silently skip failed downloads

    embedded_md = "".join(embedded_lines)
    referenced_md = "".join(referenced_lines)
else:
    # Normal mode: replace inline image tags in Docling Markdown
    embedded_md = raw_md
    referenced_md = raw_md

    for alt, raw_url in matches:
        clean_url = raw_url.strip()
        cache_item = url_cache.get(clean_url)

        if cache_item:
            filename, data_uri = cache_item
            old_tag = f"![{alt}]({raw_url})"

            # File embedded: dùng data URI
            embedded_md = embedded_md.replace(old_tag, f"![{alt}]({data_uri})")

            # File referenced: dùng relative link
            relative_path = f"./images/{filename}"
            referenced_md = referenced_md.replace(old_tag, f"![{alt}]({relative_path})")

# ==========================================
# 5. XUẤT RA FILE HOÀN CHỈNH
# ==========================================
embedded_path = OUTPUT_DIR / "article_embedded.md"
with open(embedded_path, "w", encoding="utf-8") as f:
    f.write(embedded_md)

referenced_path = OUTPUT_DIR / "article_referenced.md"
with open(referenced_path, "w", encoding="utf-8") as f:
    f.write(referenced_md)

print("\n" + "=" * 50)
print(f"[DONE] Embedded file   : {embedded_path.resolve()}")
print(f"[DONE] Referenced file : {referenced_path.resolve()}")
print(f"[DONE] Images folder   : {IMAGES_DIR.resolve()}")
print(f"[DONE] Images downloaded: {img_counter - 1}")
print("=" * 50)