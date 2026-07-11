from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from xentry.config import load_config_text, normalize_config
from xentry.decode import decode_entry
from xentry.errors import ConfigError, FragmentError, UnsupportedConfigField
from xentry.fragments import bytes_to_bits, parse_hex_bytes


CONFIG = {
    "name": "entry",
    "version": 1,
    "total_bits": 20,
    "fragment_byte_order": "msb_first",
    "bit_numbering": "byte_lsb0",
    "fields": [
        {"name": "opcode", "bits": "[3:0]"},
        {"name": "cross", "bits": "[15:8]"},
        {"name": "tail", "bits": "[19:16]"},
    ],
}


class ConfigTests(unittest.TestCase):
    def test_yaml_subset(self):
        cfg = load_config_text(
            """
name: entry
version: 1
total_bits: 8
fragment_byte_order: msb_first
bit_numbering: byte_lsb0
fields:
  - name: low
    bits: "[3:0]"
"""
        )
        config, warnings = normalize_config(cfg)
        self.assertEqual(config.name, "entry")
        self.assertEqual(config.fields[0].width, 4)
        self.assertEqual(warnings, [])

    def test_invalid_bits(self):
        cfg = dict(CONFIG)
        cfg["fields"] = [{"name": "bad", "bits": "[0:3]"}]
        with self.assertRaises(ConfigError):
            normalize_config(cfg)

    def test_unsupported_type(self):
        cfg = dict(CONFIG)
        cfg["fields"] = [{"name": "bad", "bits": "[0:0]", "type": "bool"}]
        with self.assertRaises(UnsupportedConfigField):
            normalize_config(cfg)

    def test_overlap_warning(self):
        cfg = dict(CONFIG)
        cfg["fields"] = [{"name": "a", "bits": "[3:0]"}, {"name": "b", "bits": "[2:1]"}]
        _, warnings = normalize_config(cfg)
        self.assertEqual(warnings[0]["code"], "FIELD_OVERLAP")


class FragmentTests(unittest.TestCase):
    def test_parse_hex_bytes(self):
        self.assertEqual(parse_hex_bytes("0x1122_33"), bytes.fromhex("112233"))
        self.assertEqual(parse_hex_bytes("11 22 33"), bytes.fromhex("112233"))
        with self.assertRaises(FragmentError):
            parse_hex_bytes("abc")

    def test_byte_order_and_numbering(self):
        self.assertEqual(bytes_to_bits(bytes.fromhex("80"), "lsb_first", "byte_lsb0")[7], 1)
        self.assertEqual(bytes_to_bits(bytes.fromhex("80"), "lsb_first", "byte_msb0")[0], 1)
        self.assertEqual(bytes_to_bits(bytes.fromhex("1234"), "msb_first", "byte_lsb0")[0], 0x34 & 1)
        self.assertEqual(bytes_to_bits(bytes.fromhex("1234"), "lsb_first", "byte_lsb0")[0], 0x12 & 1)


class DecodeTests(unittest.TestCase):
    def test_decode_cross_fragment(self):
        payload = decode_entry(
            CONFIG,
            [
                {"seq": 0, "data": "0x1234", "valid_lsb": 0, "valid_width": 12, "source": "a"},
                {"seq": 1, "data": "0xab", "valid_lsb": 0, "valid_width": 8, "source": "b"},
            ],
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry_raw"], "0xab234")
        self.assertEqual(payload["fields"]["opcode"]["raw_hex"], "0x4")
        self.assertEqual(payload["fields"]["cross"]["source"][0]["seq"], 0)
        self.assertEqual(payload["fields"]["cross"]["source"][1]["seq"], 1)
        self.assertEqual(payload["fields"]["tail"]["raw_hex"], "0xa")

    def test_total_bits_mismatch(self):
        with self.assertRaises(FragmentError):
            decode_entry(CONFIG, [{"seq": 0, "data": "0x12", "valid_lsb": 0, "valid_width": 8}])

    def test_valid_range_overflow(self):
        with self.assertRaises(FragmentError):
            decode_entry(CONFIG, [{"seq": 0, "data": "0x12", "valid_lsb": 4, "valid_width": 9}])


class CliTests(unittest.TestCase):
    def run_cli(self, *args, input_text=None):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        proc = subprocess.run(
            [sys.executable, "-m", "xentry.cli", *args],
            cwd=str(ROOT),
            env=env,
            input=input_text,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return json.loads(proc.stdout)

    def test_json_stdin(self):
        request = {"api_version": "xentry.v1", "action": "decode", "config": CONFIG, "fragments": [
            {"seq": 0, "data": "0x1234", "valid_lsb": 0, "valid_width": 12},
            {"seq": 1, "data": "0xab", "valid_lsb": 0, "valid_width": 8},
        ]}
        payload = self.run_cli("--json", "-", input_text=json.dumps(request))
        self.assertTrue(payload["ok"])

    def test_json_arg(self):
        request = {"api_version": "xentry.v1", "action": "explain", "config": CONFIG}
        payload = self.run_cli("--json", json.dumps(request))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "explain")

    def test_json_file(self):
        request = {"api_version": "xentry.v1", "action": "validate", "config": CONFIG}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            json.dump(request, fh)
            path = fh.name
        try:
            payload = self.run_cli("--json", path)
            self.assertTrue(payload["ok"])
        finally:
            os.unlink(path)

    def test_xout_default(self):
        request = {"api_version": "xentry.v1", "action": "explain", "config": CONFIG}
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        proc = subprocess.run(
            [sys.executable, "-m", "xentry.cli", json.dumps(request)],
            cwd=str(ROOT),
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertTrue(proc.stdout.startswith("@xentry.explain.v1"))

    def test_compat_decode(self):
        payload = self.run_cli("decode", "--config", "examples/entry.yaml", "--input", "examples/fragments.jsonl", "--json")
        self.assertTrue(payload["ok"])

    def test_compat_explain(self):
        payload = self.run_cli("explain", "--config", "examples/entry.yaml", "--json")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "explain")

    def test_compat_validate(self):
        payload = self.run_cli("validate", "--config", "examples/entry.yaml", "--input", "examples/fragments.jsonl", "--json")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "validate")


if __name__ == "__main__":
    unittest.main()
