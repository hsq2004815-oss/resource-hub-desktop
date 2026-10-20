"""Favicon cache: ICO → PNG conversion, link parsing and the on-disk cache."""

from __future__ import annotations

import http.server
import json
import struct
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

from resource_hub_core.favicons import (
    FaviconStore,
    _icon_candidates,
    _ico_to_png,
    _normalize,
    host_key,
    load_icon,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_pixels(data: bytes) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    """Decode the RGBA PNG written by the converter (filter 0 only)."""
    assert data.startswith(PNG_MAGIC)
    position = 8
    width = height = 0
    idat = b""
    while position < len(data):
        length = struct.unpack_from(">I", data, position)[0]
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        if kind == b"IHDR":
            width, height = struct.unpack_from(">II", payload)
        elif kind == b"IDAT":
            idat += payload
        position += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 4
    rows: list[list[tuple[int, int, int, int]]] = []
    for y in range(height):
        start = y * (stride + 1) + 1
        row = raw[start : start + stride]
        rows.append(
            [tuple(row[x * 4 : x * 4 + 4]) for x in range(width)]  # type: ignore[arg-type]
        )
    return width, height, rows


def make_ico(
    width: int,
    height: int,
    bit_count: int,
    top_down_rows: list[list[tuple[int, ...]]],
    mask_rows: list[bytes] | None = None,
) -> bytes:
    """A one-entry ICO with a BMP (DIB) icon; pixels are row-major, top down."""
    row_stride = ((width * bit_count + 31) // 32) * 4
    xor = bytearray()
    for row in reversed(top_down_rows):
        raw = bytearray()
        for pixel in row:
            if bit_count == 32:
                raw += bytes((pixel[2], pixel[1], pixel[0], pixel[3]))  # BGRA
            elif bit_count == 24:
                raw += bytes((pixel[2], pixel[1], pixel[0]))  # BGR
            else:
                raw += bytes(pixel)
        raw += b"\x00" * (row_stride - len(raw))
        xor += raw
    mask_stride = ((width + 31) // 32) * 4
    mask = bytearray()
    for row in reversed(mask_rows or [b"\x00" * mask_stride for _ in range(height)]):
        mask += row + b"\x00" * (mask_stride - len(row))
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height * 2,
        1,
        bit_count,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    dib = header + bytes(xor) + bytes(mask)
    entry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, bit_count, len(dib), 22)
    return struct.pack("<HHH", 0, 1, 1) + entry + dib


class IcoTests(unittest.TestCase):
    def test_bgra_icon_becomes_png(self) -> None:
        pixels = [
            [(255, 0, 0, 255), (0, 255, 0, 255)],
            [(0, 0, 255, 255), (0, 0, 0, 0)],
        ]
        data = make_ico(2, 2, 32, pixels)
        png = _ico_to_png(data)
        self.assertIsNotNone(png)
        width, height, rows = png_pixels(png or b"")
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rows[0][0], (255, 0, 0, 255))
        self.assertEqual(rows[0][1], (0, 255, 0, 255))
        self.assertEqual(rows[1][0], (0, 0, 255, 255))
        self.assertEqual(rows[1][1], (0, 0, 0, 0))

    def test_and_mask_makes_low_bit_depth_pixels_transparent(self) -> None:
        pixels = [
            [(255, 0, 0), (0, 255, 0)],
            [(0, 0, 255), (255, 255, 0)],
        ]
        # Top-left corner is transparent through the AND mask.
        data = make_ico(2, 2, 24, pixels, [b"\x80\x00\x00\x00", b"\x00\x00\x00\x00"])
        png = _ico_to_png(data)
        self.assertIsNotNone(png)
        _, _, rows = png_pixels(png or b"")
        self.assertEqual(rows[0][0][3], 0)
        self.assertEqual(rows[0][1], (0, 255, 0, 255))

    def test_normalize_keeps_png_and_rejects_junk(self) -> None:
        png = make_ico(1, 1, 32, [[(1, 2, 3, 255)]])
        converted = _normalize(_ico_to_png(png) or b"")
        self.assertIsNotNone(converted)
        assert converted is not None
        self.assertEqual(converted[1], "png")
        self.assertIsNone(_normalize(b"<html>not an image</html>"))
        self.assertIsNone(_normalize(b""))


class LinkParsingTests(unittest.TestCase):
    def test_prefers_apple_touch_then_large_png_then_ico(self) -> None:
        page = b"""
        <html><head>
        <link rel="icon" href="/small.png" sizes="16x16">
        <link rel="mask-icon" href="/mask.svg">
        <link rel="shortcut icon" href="/favicon.ico">
        <link rel="apple-touch-icon" href="/touch.png" sizes="180x180">
        <link rel="icon" type="image/png" href="/big.png" sizes="64x64">
        <link rel="icon" type="image/svg+xml" href="/icon.svg">
        </head></html>
        """
        candidates = _icon_candidates(page, "https://example.test/")
        self.assertEqual(candidates[0], "https://example.test/touch.png")
        self.assertEqual(candidates[1], "https://example.test/big.png")
        self.assertEqual(candidates[2], "https://example.test/small.png")
        self.assertEqual(candidates[-1], "https://example.test/favicon.ico")
        self.assertNotIn("https://example.test/icon.svg", candidates)

    def test_host_key_ignores_scheme_path_and_case(self) -> None:
        self.assertEqual(host_key("https://GitHub.com/a/b"), "github.com")
        self.assertEqual(host_key("github.com"), "github.com")
        self.assertEqual(host_key(""), "")
        self.assertEqual(host_key("not a url"), "")


class _IconHandler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []
    png = b""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.hits.append(self.path)
        if self.path == "/":
            body = b'<html><link rel="icon" href="/favicon.png"></html>'
            kind = "text/html"
        elif self.path == "/favicon.png":
            body = self.png
            kind = "image/png"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.png = _normalize(make_ico(1, 1, 32, [[(9, 8, 7, 255)]]))[0]  # type: ignore[index]
        self.handler = type(
            "Handler", (_IconHandler,), {"hits": [], "png": self.png}
        )
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/page"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._tmp.cleanup()

    def test_downloads_once_and_survives_a_restart(self) -> None:
        store = FaviconStore(self.dir)
        icons = store.refresh([self.url])
        self.assertIn("127.0.0.1", icons)
        path = Path(icons["127.0.0.1"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), self.png)
        self.assertEqual(
            json.loads((self.dir / "favicons" / "index.json").read_text("utf-8"))[
                "version"
            ],
            1,
        )
        hits = len(self.handler.hits)
        self.assertGreater(hits, 0)

        restarted = FaviconStore(self.dir)
        restarted.refresh([self.url])
        self.assertEqual(len(self.handler.hits), hits)  # cached, no second request

    def test_unknown_host_returns_no_icon(self) -> None:
        store = FaviconStore(self.dir)
        self.assertEqual(store.paths(), {})
        self.assertIsNone(load_icon("ftp://example.test/page"))
        self.assertIsNone(load_icon(""))


if __name__ == "__main__":
    unittest.main()
