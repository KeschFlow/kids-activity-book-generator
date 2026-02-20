cat > scaffold_repo_finalize.py <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path.cwd()

DEV_FILES = [
    "app_trainer.py",
    "analytics_app.py",
    "app_backup_logo_patch.py",
    "cover_collage.py",
    "deploy_start_redirect.sh",
    "deploy_v5102_qrstart.sh",
]

MAKEFILE_CONTENT = """dev:
\tstreamlit run app.py --server.address 0.0.0.0 --server.port 8501

prod:
\tEPE_ENV=prod streamlit run app.py --server.address 0.0.0.0 --server.port 8501

ci:
\truff check .
\tpython -c "import app; print('Import OK')"
"""

README_CHECKLIST = """

---

## 🚀 Production Checklist

- [ ] EPE_ENV=prod gesetzt
- [ ] Streamlit Cloud Secrets konfiguriert
- [ ] Upload Limits getestet (12MB / 160MB)
- [ ] 24 Bilder Testlauf erfolgreich
- [ ] Doppel-Click Lock getestet
- [ ] PDF Download validiert
- [ ] KDP Upload Smoke-Test durchgeführt
- [ ] CI läuft grün
"""

GITIGNORE_ADDITIONS = [
    ".venv/",
    "__pycache__/",
    "*.bak_*",
    ".DS_Store",
]

def move_dev_files() -> None:
    dev_dir = ROOT / "dev"
    dev_dir.mkdir(exist_ok=True)
    for fname in DEV_FILES:
        f = ROOT / fname
        if f.exists():
            target = dev_dir / fname
            print(f"→ move {fname} -> dev/{fname}")
            shutil.move(str(f), str(target))

def create_makefile() -> None:
    makefile = ROOT / "Makefile"
    if not makefile.exists():
        makefile.write_text(MAKEFILE_CONTENT, encoding="utf-8")
        print("→ created Makefile")

def patch_readme() -> None:
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    content = readme.read_text(encoding="utf-8")
    if "Production Checklist" not in content:
        readme.write_text(content + README_CHECKLIST, encoding="utf-8")
        print("→ appended Production Checklist to README.md")

def patch_gitignore() -> None:
    gi = ROOT / ".gitignore"
    content = gi.read_text(encoding="utf-8") if gi.exists() else ""
    changed = False
    for line in GITIGNORE_ADDITIONS:
        if line not in content:
            content += ("\n" if content and not content.endswith("\n") else "") + line + "\n"
            changed = True
    if changed or not gi.exists():
        gi.write_text(content, encoding="utf-8")
        print("→ updated .gitignore")

def main() -> None:
    move_dev_files()
    create_makefile()
    patch_readme()
    patch_gitignore()
    print("\n✅ Repo finalize done.")
    print("Next: git status")

if __name__ == "__main__":
    main()
PY

python scaffold_repo_finalize.py
