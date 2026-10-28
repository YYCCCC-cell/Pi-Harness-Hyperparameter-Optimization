"""Restore exact upstream commits. Downloads source only; never runs/install it."""

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / "docs/sources/source_lock.json").read_text())
    for repo in lock["repositories"]:
        path = ROOT / repo["directory"]
        if not path.exists():
            path.mkdir(parents=True)
            subprocess.run(["git", "init", str(path)], check=True)
            subprocess.run(["git", "-C", str(path), "remote", "add", "origin", repo["canonical_url"] + ".git"], check=True)
            subprocess.run(["git", "-C", str(path), "fetch", "--depth=1", "origin", repo["commit"]], check=True)
            subprocess.run(["git", "-C", str(path), "checkout", "--detach", repo["commit"]], check=True)
        actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
        if actual != repo["commit"] or dirty:
            raise RuntimeError(f"Existing checkout differs: {path}. No reset or overwrite was performed.")
        print(f"Verified {repo['directory']} at {actual}")


if __name__ == "__main__":
    main()
