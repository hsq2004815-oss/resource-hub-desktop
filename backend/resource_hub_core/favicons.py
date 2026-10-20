"""Cached site icons for the Flutter link cards.

Downloads one icon per site (best effort, once), converts the ``.ico`` container
to PNG — Flutter cannot decode ICO — and keeps the result under
``data/favicons`` so later launches render icons without the network.

Fetching is deliberately simple: read the home page, try the ``<link rel=icon>``
targets in preference order, then ``/apple-touch-icon.png`` and ``/favicon.ico``.
Sites that fail just keep the generic per-kind glyph in the UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import threading
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_TIMEOUT = 4.0
_MAX_PAGE_BYTES = 300 * 1024
_MAX_ICON_BYTES = 512 * 1024
_MAX_CANDIDATES = 8
_WORKERS = 4
_INDEX_VERSION = 1
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: link rel tokens that qualify as a site icon (``mask-icon`` is SVG on purpose).
_ICON_RELS = {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"}


def host_key(url: str) -> str:
    """Cache key for a site URL (``https://GitHub.com/x`` → ``github.com``)."""
    text = (url or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text if "://" in text else "https://" + text)
    except ValueError:
        return ""
    host = (parts.hostname or "").casefold()
    return "" if any(char.isspace() for char in host) else host


class _IconLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        data = {name.casefold(): (value or "") for name, value in attrs}
        rel = data.get("rel", "")
        href = data.get("href", "").strip()
        if not href or not rel:
            return
        tokens = set(rel.casefold().split())
        if tokens & _ICON_RELS:
            self.links.append(
                (rel, href, data.get("type", ""), data.get("sizes", ""))
            )


def _fetch(url: str, limit: int) -> bytes | None:
    """GET a URL, capped at `limit` bytes. Never raises."""
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.read(limit)
    except Exception:  # noqa: BLE001 - any failure just skips this candidate
        return None


def _icon_candidates(page: bytes, base: str) -> list[str]:
    """Icon URLs declared by the page, most useful first."""
    parser = _IconLinkParser()
    try:
        parser.feed(page.decode("utf-8", "ignore"))
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup just yields nothing
        return []
    ranked: list[tuple[tuple[int, int, int], str]] = []
    for order, (rel, href, kind, sizes) in enumerate(parser.links):
        if href.casefold().startswith("data:"):
            continue
        kind = kind.casefold()
        extension = href.split("?", 1)[0].rsplit(".", 1)[-1].casefold()
        if "svg" in kind or extension == "svg":
            continue  # vector icons need a rasteriser Flutter does not ship.
        tokens = set(rel.casefold().split())
        size_match = re.search(r"(\d+)\s*x\s*(\d+)", sizes)
        size = int(size_match.group(1)) if size_match else 16
        if tokens & {"apple-touch-icon", "apple-touch-icon-precomposed"}:
            rank = 0  # biggest, already raster, present on most sites.
        elif "png" in kind or extension == "png":
            rank = 1
        elif "ico" in kind or extension == "ico":
            rank = 3
        else:
            rank = 2
        ranked.append(((rank, -size, order), urljoin(base, href)))
    ranked.sort()
    return [url for _, url in ranked]


def _normalize(data: bytes) -> tuple[bytes, str] | None:
    """``(bytes, extension)`` for a Flutter-decodable image, else ``None``."""
    if not data:
        return None
    if data.startswith(_PNG_MAGIC):
        return data, "png"
    if data[:3] == b"\xff\xd8\xff":
        return data, "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return data, "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "webp"
    if data[:4] == b"\x00\x00\x01\x00":
        png = _ico_to_png(data)
        if png is not None:
            return png, "png"
    return None


def load_icon(url: str) -> tuple[bytes, str] | None:
    """Download and convert the best icon for `url` (`None` when none works)."""
    try:
        parts = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    base = f"{parts.scheme}://{parts.netloc}/"
    candidates: list[str] = []
    page = _fetch(base, _MAX_PAGE_BYTES)
    if page:
        candidates.extend(_icon_candidates(page, base))
    candidates.append(urljoin(base, "/apple-touch-icon.png"))
    candidates.append(urljoin(base, "/favicon.ico"))
    seen: set[str] = set()
    attempts = 0
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        attempts += 1
        if attempts > _MAX_CANDIDATES:
            break
        image = _normalize(_fetch(candidate, _MAX_ICON_BYTES) or b"")
        if image is not None:
            return image
    return None


# -- ICO → PNG --------------------------------------------------------------


def _ico_to_png(data: bytes) -> bytes | None:
    """Convert an ICO container to PNG, picking the largest embedded image."""
    try:
        count = struct.unpack_from("<H", data, 4)[0]
    except struct.error:
        return None
    best: tuple[int, int, int, bytes] | None = None
    for index in range(min(count, 64)):
        try:
            width, height, _, _, _, _, size, offset = struct.unpack_from(
                "<BBBBHHII", data, 6 + index * 16
            )
        except struct.error:
            break
        if size < 40 or offset + size > len(data):
            continue
        width = width or 256
        height = height or 256
        if width > 256 or height > 256:
            continue
        area = width * height
        if best is None or area > best[0]:
            best = (area, width, height, data[offset : offset + size])
    if best is None:
        return None
    _, width, height, image = best
    if image.startswith(_PNG_MAGIC):
        return image  # newer .ico files embed a PNG verbatim.
    return _dib_to_png(image, width, height)


def _dib_to_png(dib: bytes, width: int, height: int) -> bytes | None:
    """Decode the DIB stored inside an ICO and re-encode it as PNG."""
    if len(dib) < 40:
        return None
    try:
        (
            header_size,
            bitmap_width,
            bitmap_height,
            _planes,
            bit_count,
            compression,
            _image_size,
            _x_ppm,
            _y_ppm,
            colors_used,
            _important,
        ) = struct.unpack_from("<IiiHHIIiiII", dib, 0)
    except struct.error:
        return None
    if compression != 0 or bit_count not in (1, 4, 8, 24, 32):
        return None
    if bitmap_width <= 0 or bitmap_height == 0:
        return None
    # ICO stores twice the real height (colour bitmap + AND mask).
    width = min(width, bitmap_width)
    height = min(height, abs(bitmap_height) // 2 or abs(bitmap_height))
    if width <= 0 or height <= 0:
        return None

    palette_count = colors_used or (1 << bit_count if bit_count <= 8 else 0)
    palette_offset = header_size
    offset = palette_offset + 4 * palette_count
    stride = ((width * bit_count + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    mask_offset = offset + stride * height
    has_mask = mask_offset + mask_stride * height <= len(dib)
    if not has_mask:
        mask_offset = 0
    if offset + stride * height > len(dib):
        return None

    # A 32 bpp icon with an all-zero alpha channel (old writers) still needs the
    # AND mask for transparency.
    xor_has_alpha = bit_count == 32 and any(
        dib[offset + row * stride + column * 4 + 3]
        for row in range(height)
        for column in range(width)
    )

    pixels = bytearray(width * height * 4)
    for y in range(height):
        row = offset + stride * (height - 1 - y)
        mask_row = (
            mask_offset + mask_stride * (height - 1 - y) if has_mask else 0
        )
        for x in range(width):
            if bit_count == 32:
                index = None
                b, g, r, alpha = dib[row + x * 4 : row + x * 4 + 4]
            elif bit_count == 24:
                index = None
                b, g, r = dib[row + x * 3 : row + x * 3 + 3]
                alpha = 255
            elif bit_count == 8:
                index = dib[row + x]
                b = g = r = alpha = 0
            elif bit_count == 4:
                byte = dib[row + x // 2]
                index = (byte >> 4) & 0xF if x % 2 == 0 else byte & 0xF
                b = g = r = alpha = 0
            else:  # 1 bpp
                byte = dib[row + x // 8]
                index = (byte >> (7 - x % 8)) & 1
                b = g = r = alpha = 0
            if index is not None:
                entry = palette_offset + index * 4
                if entry + 4 > len(dib):
                    return None
                b, g, r = dib[entry], dib[entry + 1], dib[entry + 2]
                alpha = 255
            if has_mask:
                mask_byte = dib[mask_row + x // 8]
                if (mask_byte >> (7 - x % 8)) & 1:
                    alpha = 0
                elif bit_count != 32 or not xor_has_alpha:
                    alpha = 255
            base = (y * width + x) * 4
            pixels[base] = r
            pixels[base + 1] = g
            pixels[base + 2] = b
            pixels[base + 3] = alpha
    return _encode_png(width, height, bytes(pixels))


def _encode_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        _PNG_MAGIC
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


# -- cache ------------------------------------------------------------------


class FaviconStore:
    """``data/favicons`` files plus an ``index.json`` host → file name map."""

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.dir = Path(base_dir) / "favicons"
        self.index_path = self.dir / "index.json"
        self._lock = threading.Lock()
        self._icons = self._load_index()

    def _load_index(self) -> dict[str, str]:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        icons = data.get("icons") if isinstance(data, dict) else None
        if not isinstance(icons, dict):
            return {}
        return {
            str(host): str(name)
            for host, name in icons.items()
            if isinstance(host, str) and isinstance(name, str)
        }

    def _save_index(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"version": _INDEX_VERSION, "icons": self._icons},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.index_path)

    def paths(self) -> dict[str, str]:
        """Host → absolute icon path, only for files that still exist."""
        with self._lock:
            icons = dict(self._icons)
        return {
            host: str(self.dir / name)
            for host, name in icons.items()
            if (self.dir / name).is_file()
        }

    def refresh(self, urls: list[str]) -> dict[str, str]:
        """Fetch icons for hosts not cached yet. Blocking; call off the UI thread."""
        with self._lock:
            known = dict(self._icons)
        wanted: dict[str, str] = {}
        for url in urls:
            host = host_key(url)
            if host and host not in known and host not in wanted:
                wanted[host] = url
        if not wanted:
            return self.paths()
        self.dir.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            fetched = list(pool.map(load_icon, wanted.values()))
        with self._lock:
            for host, image in zip(wanted, fetched):
                if image is None:
                    continue
                data, extension = image
                name = hashlib.sha1(host.encode("utf-8")).hexdigest()[:20]
                name = f"{name}.{extension}"
                try:
                    (self.dir / name).write_bytes(data)
                except OSError:
                    continue
                self._icons[host] = name
            if self._icons != known:
                try:
                    self._save_index()
                except OSError:
                    pass
        return self.paths()
