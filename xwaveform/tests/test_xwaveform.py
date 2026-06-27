import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from xwaveform.loader import load_manifest, load_signal
from xwaveform.loader import SignalData
from xwaveform.render import _format_time_ns, _plot_left, _text_width, _value_y_positions, render_waveform


class XwaveformTest(unittest.TestCase):
    def _write_u64bin(self, path, rows, word_count=1):
        with path.open("wb") as f:
            for row in rows:
                time_tick, value_words, known_words = row
                f.write(struct.pack("<Q", time_tick))
                for word in value_words:
                    f.write(struct.pack("<Q", word))
                for word in known_words:
                    f.write(struct.pack("<Q", word))

    def _write_manifest(self, root, signals):
        manifest = {
            "version": 1,
            "format": "u64bin.v1",
            "list": "basic",
            "begin": "0ns",
            "end": "256ns",
            "signals": signals,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    def test_load_and_render_u64bin(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "sig.u64bin"
            self._write_u64bin(data, [
                (0, [0], [1]),
                (128000, [1], [1]),
                (256000, [0], [1]),
            ])
            manifest_path = self._write_manifest(root, [{
                    "index": 0,
                    "signal": "top.sig",
                    "file": "sig.u64bin",
                    "row_count": 3,
                    "width": 1,
                    "word_count": 1,
                    "columns": 3,
                }])
            loaded = load_manifest(manifest_path)
            sig = load_signal(loaded, "top.sig")
            self.assertEqual(sig.row_count, 3)
            out = root / "wave.jpg"
            result = render_waveform(manifest_path, out, width=4096)
            self.assertTrue(out.exists())
            self.assertEqual(result["width"], 4096)
            stats = json.loads((root / "wave.jpg.stats.json").read_text())
            self.assertEqual(stats["signals"][0]["min_hex"], "0x0")
            self.assertEqual(stats["signals"][0]["max_hex"], "0x1")

    def test_render_numeric_values_and_alternating_background(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_u64bin(root / "sig_a.u64bin", [
                (0, [0], [0xff]),
                (128000, [7], [0xff]),
                (256000, [3], [0xff]),
            ])
            self._write_u64bin(root / "sig_b.u64bin", [
                (0, [1], [0xff]),
                (128000, [2], [0xff]),
                (256000, [1], [0xff]),
            ])
            manifest_path = self._write_manifest(root, [
                {
                    "index": 0,
                    "signal": "top.sig_a",
                    "file": "sig_a.u64bin",
                    "row_count": 3,
                    "width": 8,
                    "word_count": 1,
                    "columns": 3,
                },
                {
                    "index": 1,
                    "signal": "top.sig_b",
                    "file": "sig_b.u64bin",
                    "row_count": 3,
                    "width": 8,
                    "word_count": 1,
                    "columns": 3,
                },
            ])
            out = root / "wave.jpg"
            result = render_waveform(manifest_path, out, width=512, height_per_signal=24, quality=100)
            self.assertEqual(result["signal_count"], 2)
            stats = json.loads((root / "wave.jpg.stats.json").read_text())
            self.assertEqual(stats["signals"][0]["min_hex"], "0x0")
            self.assertEqual(stats["signals"][0]["max_hex"], "0x7")
            image = Image.open(out).convert("RGB")
            row0 = image.getpixel((4, 50))
            row1 = image.getpixel((4, 74))
            self.assertNotEqual(row0, row1)
            self.assertLess(sum(row1), sum(row0))

    def test_value_plot_uses_full_width_words(self):
        data = SignalData(
            signal="top.wide",
            time_tick=np.array([0, 128000, 256000], dtype=np.uint64),
            value_words=np.array([[0, 0], [0, 1], [0, 2]], dtype=np.uint64),
            known_words=np.array([[0xffffffffffffffff, 0xffffffffffffffff],
                                  [0xffffffffffffffff, 0xffffffffffffffff],
                                  [0xffffffffffffffff, 0xffffffffffffffff]], dtype=np.uint64),
            width=128,
            word_count=2,
            row_count=3,
        )
        ys, known = _value_y_positions(data, high=10, low=30, mid=20)
        self.assertTrue(known.all())
        self.assertEqual(ys.tolist(), [30, 20, 10])

    def test_cursor_time_labels_use_ns(self):
        self.assertEqual(_format_time_ns(0), "0ns")
        self.assertEqual(_format_time_ns(1000), "1ns")
        self.assertEqual(_format_time_ns(145455), "145.455ns")
        self.assertEqual(_format_time_ns(1_000_000), "1000ns")

    def test_plot_left_tracks_label_right_edge(self):
        image = Image.new("RGB", (512, 128), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        signals = [
            {"signal": "top.short"},
            {"signal": "very.long.hierarchy.u_subsystem.u_block.u_if.payload_valid"},
        ]
        expected = 8 + _text_width(draw, signals[1]["signal"][-48:], font) + 30
        self.assertEqual(_plot_left(draw, signals, font), expected)


if __name__ == "__main__":
    unittest.main()
