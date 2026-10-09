"""Fails (exit 1) if any banned term appears in the repository outside `.git`.

Terms are stored only as salted SHA-256 prefixes, so this file itself contains none of them.
Every file (and every path) is tokenised into lowercase alphanumeric words; each word and each
adjacent word pair is hashed and compared against the banned sets.

Usage:
    python scripts/check_branding.py            # scan the repo
    python scripts/check_branding.py --hash "some term"   # print the hash for a new term
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SALT = "granth-brand:"
DIGEST_LEN = 20

BANNED_WORDS = {
    "06a3cd633abcd4d747aa", "0a34bc746412a3565dbf", "0b9d261fa5ca11044983", "13502452674990ffdfb6",
    "2277694f48a325325ec2", "22b97f94ffe8b389bf39", "32a0ba42426a65485b33", "47308d8615f977990d64",
    "4a38f7a687792621b8ee", "566db8d99b446684d627", "5853eaf4ba7d83cd8dd8", "5b83396c71e86c98240a",
    "6bb1c469ce6b1dee9f85", "73dfd0b7df2e1c0e8ba8", "745fc20637085e5577b4", "7e86b1610f9a2235dd98",
    "7f24e2aa7ca1ef1d21ac", "86d6dc9c6adbfab98eef", "939db91b01231925c5f7", "98309d9a0b8aad5b0edd",
    "9c9688071d6151e9c7eb", "add49a68384aec834c09", "b0b314954e1007836388", "b5aeef9bb607fea6816f",
    "b80a00d6c861fd024713", "b9b3070f4c316e2410eb", "bb302016e39d829a6359", "bfdb63f95cea70f1380c",
    "c24377376657ccc55b0c", "d2f7edf136d40f3c572d", "ed32aca756eddeb8ee23", "ed90776f2db2ccb45e5d",
    "f9e32ba94ddf1b72a35e", "fd767b3f3e5b3ec20909",
}
BANNED_PAIRS = {
    "154e0a7868661a02f5d7", "22ef7c0bae8c20791d51", "26943fa4aaa95b675e2b", "2cc75e6f065700e38785",
    "36b3d378cdf9748b5b18", "53abcdda9ebdf5aeccc2", "63166a4495779c492d7e", "679b9e84529c78bc0f58",
    "bc3d8fb9d7dcf16c1428", "c6e4b1d61fb07db26056", "d5207d0d44f76337627f",
}

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "data", "dist", "__pycache__", ".pytest_cache",
             ".mypy_cache", ".claude"}
# Internal working documents (not part of the submission) that necessarily name the terms.
ALLOWLIST = {"docs/AUDIT.md", "docs/PLAN.md"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".onnx", ".bin",
              ".sqlite", ".db", ".pyc", ".zip"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_LOCK_NOISE_RE = re.compile(r'^\s*"(?:integrity|license)":.*$', re.MULTILINE)


def _h(term: str) -> str:
    return hashlib.sha256((SALT + term).encode()).hexdigest()[:DIGEST_LEN]


def scan_text(text: str):
    """Yields (line_no, matched_text) for every banned word or word pair in `text`."""
    for line_no, line in enumerate(text.lower().splitlines(), start=1):
        toks = _TOKEN_RE.findall(line)
        for i, t in enumerate(toks):
            if _h(t) in BANNED_WORDS:
                yield line_no, t
            if i + 1 < len(toks) and _h(f"{t} {toks[i + 1]}") in BANNED_PAIRS:
                yield line_no, f"{t} {toks[i + 1]}"


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.is_file():
            yield p, rel.as_posix()


def main(argv) -> int:
    if len(argv) >= 2 and argv[0] == "--hash":
        term = " ".join(_TOKEN_RE.findall(" ".join(argv[1:]).lower()))
        print(_h(term))
        return 0

    root = Path(argv[0]).resolve() if argv else ROOT
    hits = []
    scanned = 0
    for path, rel in iter_files(root):
        if rel in ALLOWLIST:
            continue
        for _, m in scan_text(rel.replace("/", " ")):
            hits.append((rel, 0, m))
        if path.suffix.lower() in BINARY_EXT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if path.name == "package-lock.json":
            text = _LOCK_NOISE_RE.sub("", text)
        scanned += 1
        for line_no, m in scan_text(text):
            hits.append((rel, line_no, m))

    for rel, line_no, m in hits:
        print(f"{rel}:{line_no}: banned term '{m}'")
    print(f"check_branding: scanned {scanned} files, {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
