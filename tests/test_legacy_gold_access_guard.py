from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_ENTRYPOINTS = [
    "scripts/create_dataset_v2.py",
    "scripts/train_polar_gpu.py",
    "scripts/independent_snr_audit.py",
    "scripts/audit_overlap.py",
    "scripts/test_mutation.py",
    "scripts/run_v2_post_training_eval.py",
    "scripts/create_v2_deduplicated_manifest.py",
    "scripts/final_gunfire_validation.py",
    "scripts/evaluate_v1_v2_gold.py",
    "scripts/train_baseline.py",
    "scripts/test_data_integrity.py",
    "scripts/run_sampling_ablation.py",
    "scripts/test_determinism.sh",
    "scripts/train_polar_full.py",
    "scripts/test_v2_loader.py",
    "scripts/evaluate_gold_test.py",
    "scripts/run_full_evaluation.py",
    "scripts/train_full.py",
    "scripts/audit_defence_noise.py",
    "scripts/train_v2_25k.py",
    "scripts/freeze_gold_test.py",
    "scripts/evaluate_polar_gold.py",
    "scripts/dataset_final_audit.py",
    "scripts/audit_model_behavior.py",
    "scripts/run_sisdr_ablation.py",
]


class LegacyGoldEntryPointBlockTests(unittest.TestCase):
    def test_legacy_entry_points_exit_before_running_body(self) -> None:
        with tempfile.TemporaryDirectory(prefix="legacy-gold-guard-") as temp:
            for relative in LEGACY_ENTRYPOINTS:
                with self.subTest(entrypoint=relative):
                    path = ROOT / relative
                    command = (
                        ["bash", str(path)]
                        if path.suffix == ".sh"
                        else [sys.executable, str(path)]
                    )
                    result = subprocess.run(
                        command,
                        cwd=temp,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("BLOCKED: legacy tool", result.stderr)
                    self.assertIn(path.name, result.stderr)

    def test_guard_module_has_no_environment_override(self) -> None:
        guard = (ROOT / "scripts/legacy_gold_access_guard.py").read_text()
        self.assertNotIn("os.environ", guard)
        self.assertNotIn("getenv(", guard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
