"""End-to-end protocol test over real pipes.

Runs ``backend/main.py`` as a separate process, exactly the way the Flutter client
will, and verifies the two things unit tests cannot: the Windows stdio encoding
path (cp936 would mangle Chinese) and the LF-only framing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"


class SubprocessProtocolTests(unittest.TestCase):
    def test_roundtrip_over_real_pipes(self) -> None:
        requests = [
            {"id": 1, "method": "app.hello", "params": {}},
            {
                "id": 2,
                "method": "resources.add",
                "params": {
                    "mode": "links",
                    "name": "内部知识库",
                    "target": "wiki.example.com",
                    "note": "中文备注",
                },
            },
            {"id": 3, "method": "resources.list", "params": {"mode": "links"}},
            {"id": 4, "method": "app.shutdown", "params": {}},
        ]
        script = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(MAIN), tmp],
                input=script.encode("utf-8"),
                capture_output=True,
                timeout=60,
            )

        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        # Protocol frames only, LF-terminated, UTF-8.
        self.assertNotIn(b"\r\n", proc.stdout)
        frames = [
            json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line
        ]
        self.assertEqual([f["id"] for f in frames], [1, 2, 3, 4])
        self.assertTrue(all(f["ok"] for f in frames), frames)

        self.assertEqual(frames[0]["result"]["protocolVersion"], 1)
        self.assertEqual(frames[1]["result"]["item"]["name"], "内部知识库")
        names = [item["name"] for item in frames[2]["result"]["items"]]
        self.assertIn("内部知识库", names)
        self.assertTrue(frames[3]["result"]["shutdown"])

        # Nothing should have been logged as an internal failure.
        self.assertNotIn("[resource-hub]", proc.stderr.decode("utf-8", "replace"))

    def test_process_exits_on_stdin_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(MAIN), tmp],
                input=b"",
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")


if __name__ == "__main__":
    unittest.main()
