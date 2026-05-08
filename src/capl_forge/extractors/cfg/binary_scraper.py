"""Binary and zip .cfg path scraping."""
import re
import zipfile
from pathlib import Path

# Config: extensions grouped by role
EXTENSION_ROLES = {
    "network":     {"dbc", "ldf", "arxml"},
    "diagnostic":  {"cdd", "odx", "odx-d", "pdx", "cbf"},
    "capl":        {"can", "cin"},
    "panel":       {"xvp", "cpa", "xvb"},
    "sysvar":      {"vsysvar"},
    "testmodule":  {"vtuexe", "vtt"},
    "nodelayer":   {"dll"},
    "logging":     {"blf", "asc", "mf4", "mdf4"},
    "spec":        {"xlsx", "xlsm", "docx", "pdf"},
    "config":      {"xml", "ini", "cfg"},
}
ALL_EXTS = sorted({e for s in EXTENSION_ROLES.values() for e in s})


def ext_role(ext: str) -> str:
    """Determine the role category of a file based on its extension."""
    ext = ext.lower().lstrip(".")
    for role, exts in EXTENSION_ROLES.items():
        if ext in exts:
            return role
    return "other"


class BinaryScraper:
    """Scrapes file-path strings from CANoe .cfg files (binary and zip formats)."""

    _ABS_PATTERN = re.compile(
        r"[A-Za-z]:\\[^\x00<>\"|?*\r\n]{1,400}?\.(?:" + "|".join(ALL_EXTS) + r")",
        re.IGNORECASE,
    )
    _REL_PATTERN = re.compile(
        r"(?:\.{1,2}\\|[\w\-\. ]+\\)[^\x00<>\"|?*\r\n]{1,400}?\.(?:" + "|".join(ALL_EXTS) + r")",
        re.IGNORECASE,
    )

    def __init__(self, log=None):
        self.log = log or (lambda msg: None)

    def scrape_zip(self, cfg_path: Path) -> list[str]:
        """Extract file paths from a zipped .cfg archive."""
        self.log("Opening as zip archive...")
        refs = set()
        try:
            with zipfile.ZipFile(cfg_path) as z:
                for name in z.namelist():
                    self.log(f"  entry: {name}")
                    if name.lower().endswith((".xml", ".cfg", ".ini")):
                        try:
                            content = z.read(name).decode("utf-8", errors="ignore")
                        except Exception as e:
                            self.log(f"    (skip, read error: {e})")
                            continue
                        refs.update(self._scrape_paths(content))
        except zipfile.BadZipFile:
            self.log("BadZipFile — falling back to binary scrape")
            return self.scrape_binary(cfg_path)
        return sorted(refs)

    def scrape_binary(self, cfg_path: Path) -> list[str]:
        """Extract file paths from a binary .cfg file."""
        self.log("Reading bytes for string extraction...")
        data = cfg_path.read_bytes()
        self.log(f"Loaded {len(data):,} bytes")

        self.log("Decoding as UTF-16LE (Vector's usual encoding)...")
        text_utf16 = data.decode("utf-16-le", errors="ignore")
        self.log("Decoding as Latin-1 (ASCII-embedded fallback)...")
        text_ascii = data.decode("latin-1", errors="ignore")

        refs = set()
        self.log("Scanning UTF-16 text for path patterns...")
        refs.update(self._scrape_paths(text_utf16))
        self.log(f"  UTF-16 hits so far: {len(refs)}")

        self.log("Scanning Latin-1 text for path patterns...")
        refs.update(self._scrape_paths(text_ascii))
        self.log(f"  total hits: {len(refs)}")
        return sorted(refs)

    def _scrape_paths(self, text: str) -> set[str]:
        """Find file-path patterns in text."""
        hits = set()
        for m in self._ABS_PATTERN.findall(text):
            hits.add(m.strip())
        for m in self._REL_PATTERN.findall(text):
            hits.add(m.strip())
        cleaned = set()
        for h in hits:
            if len(h) > 400:
                continue
            if any(ord(c) < 32 for c in h):
                continue
            cleaned.add(h)
        return cleaned
