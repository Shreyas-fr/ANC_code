"""Synthetic regression tests for the canonical evaluator's gold-path guard.

These tests create only empty temporary directories named like the protected
tree; they never enumerate, open, or otherwise access the real gold dataset.
"""

from __future__ import annotations

import tempfile
import sys
import types
import unittest
from pathlib import Path

# This test exercises only the path guard. Stub the evaluator's unrelated
# scipy.signal import so the test does not depend on the project's known
# SciPy/NumPy binary-version mismatch.
scipy_stub = types.ModuleType("scipy")
scipy_signal_stub = types.ModuleType("scipy.signal")
scipy_stub.signal = scipy_signal_stub
sys.modules.setdefault("scipy", scipy_stub)
sys.modules.setdefault("scipy.signal", scipy_signal_stub)

from scripts.evaluate_dfn3_canonical import require_non_gold_canonical_dir
from scripts.audit_sih26_dataset import iter_safe_files, resolve_non_gold_path


class CanonicalGoldPathGuardTests(unittest.TestCase):
    def test_normal_non_gold_path_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-canonical-guard-") as temp:
            canonical = Path(temp) / "canonical_validation"
            canonical.mkdir()
            self.assertEqual(
                require_non_gold_canonical_dir(canonical), canonical.resolve()
            )

    def test_direct_gold_named_path_is_rejected_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-canonical-guard-") as temp:
            gold_named = Path(temp) / "sih_gold_test"
            gold_named.mkdir()
            with self.assertRaises(SystemExit):
                require_non_gold_canonical_dir(gold_named)

    def test_symlink_to_gold_named_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-canonical-guard-") as temp:
            root = Path(temp)
            gold_named = root / "SIH_GOLD_TEST"
            gold_named.mkdir()
            alias = root / "canonical_alias"
            alias.symlink_to(gold_named, target_is_directory=True)
            with self.assertRaises(SystemExit):
                require_non_gold_canonical_dir(alias)

    def test_dataset_audit_accepts_path_within_candidate_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-dataset-guard-") as temp:
            root = Path(temp) / "candidate"
            root.mkdir()
            audio = root / "speech.wav"
            audio.touch()
            self.assertEqual(
                resolve_non_gold_path(audio, root=root, strict=True), audio.resolve()
            )

    def test_dataset_audit_rejects_root_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-dataset-guard-") as temp:
            root = Path(temp) / "candidate"
            root.mkdir()
            outside = Path(temp) / "outside.wav"
            outside.touch()
            with self.assertRaises(ValueError):
                resolve_non_gold_path(outside, root=root, strict=True)

    def test_dataset_audit_rejects_symlink_into_gold_without_opening_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-dataset-guard-") as temp:
            root = Path(temp) / "candidate"
            root.mkdir()
            gold_named = Path(temp) / "SIH_GOLD_TEST"
            gold_named.mkdir()
            protected = gold_named / "sealed.wav"
            protected.write_bytes(b"synthetic sentinel; not project data")
            alias = root / "candidate.wav"
            alias.symlink_to(protected)
            with self.assertRaises(ValueError):
                resolve_non_gold_path(alias, root=root, strict=True)

    def test_dataset_audit_walker_rejects_gold_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-dataset-guard-") as temp:
            parent = Path(temp)
            root = parent / "candidate"
            root.mkdir()
            gold_named = parent / "SIH_GOLD_TEST"
            gold_named.mkdir()
            (gold_named / "sealed.wav").write_bytes(b"synthetic sentinel")
            (root / "linked_audio").symlink_to(gold_named, target_is_directory=True)
            with self.assertRaises(ValueError):
                list(iter_safe_files(root))

    def test_dataset_audit_walker_refuses_internal_directory_symlinks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sih-dataset-guard-") as temp:
            root = Path(temp) / "candidate"
            root.mkdir()
            target = root / "audio_real"
            target.mkdir()
            (target / "sample.wav").touch()
            (root / "audio_alias").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Directory symlinks are not supported"):
                list(iter_safe_files(root))


if __name__ == "__main__":
    unittest.main()
