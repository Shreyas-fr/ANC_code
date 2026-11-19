# Contributing to ANC (SIH 26052)

Thank you for contributing to the ANC Speech Enhancement repository. To ensure smooth collaboration between contributors while maintaining research rigor and code reproducibility, please adhere to these guidelines.

---

## 1. Branching Strategy

- **`main`**: The stable, production-ready branch. All code on `main` must pass tests and preserve verified baseline performance. Direct commits to `main` should be reserved for coordinated releases.
- **`feature/<name>`**: For developing new functional features, optimizations, or tooling (e.g., `feature/mvdr-optimizations`, `feature/pi5-benchmark`).
- **`experiment/<name>`**: For standalone research stages and model evaluations (e.g., `experiment/stage11_3_ablation`).
- **`fix/<name>`**: For bug fixes or portability corrections.

---

## 2. Collaborative Workflow

1. **Sync with Remote:**
   ```bash
   git fetch origin
   git checkout main
   git pull origin main
   ```

2. **Create a Topic Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Atomic Commits:**
   Follow conventional commit messages:
   - `feat:` New features or capabilities.
   - `fix:` Bug fixes or data alignment repairs.
   - `docs:` Documentation updates.
   - `test:` Unit tests or regression suites.
   - `chore:` Maintenance, dependency updates, or cleanup.

4. **Open a Pull Request:**
   Submit a PR targeting `main`. Provide a clear description of changes, metrics impact, and verification steps. Both contributors must review before merging.

---

## 3. Strict Development Rules

### Rule 1: Sealed Gold Test (`GOLD_TEST_READ = NO`)
- Under no circumstances should any contributor, script, test harness, or CI/CD workflow open, read, decode, hash, or evaluate against `data/SIH_GOLD_TEST/`.
- All development and validation must use the canonical 590-clip set or independent development datasets.

### Rule 2: Path Portability
- **Never hardcode absolute user paths** (e.g., `/Users/username/...` or `C:\Users\...`).
- Always anchor paths relative to the script or repository root using `pathlib.Path`:
  ```python
  from pathlib import Path
  REPO_ROOT = Path(__file__).resolve().parents[1]  # or appropriate parent anchor
  ```

### Rule 3: Model Weight Preservation
- Do not modify, overwrite, or re-export the frozen B0 model weights (`runs/step500_from_pi.pt`, `checkpoints/fullsubnet/...`, `checkpoints/gtcrn_stage5/...`).
- Any newly trained weights must be versioned separately under an experiment-specific path.

### Rule 4: Credential & Secret Security
- Never stage or commit private keys, tokens, `.env` files, or connection strings.
- Keep `.gitignore` updated with appropriate security exclusions (`*.key`, `*.pem`, `rpi_key*`).

---

## 4. Verification Before Submitting

Before requesting a review, verify:
1. **Python Syntax & Compilation:**
   ```bash
   python -m compileall src scripts
   ```
2. **Unit Tests:**
   ```bash
   pytest tests/
   ```
3. **No Unintended Large Binaries:**
   Verify `git status` does not include build artifacts, `.tar.gz` caches, or large model weights (>50 MB).
