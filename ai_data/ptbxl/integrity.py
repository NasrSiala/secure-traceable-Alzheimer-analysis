"""SHA-256 integrity verification for PTB-XL files."""

import hashlib
from pathlib import Path


class PTBXLIntegrityChecker:

    def __init__(self, dataset_root):
        self.root = Path(dataset_root)
        self.manifest = self.root / "SHA256SUMS.txt"

        if not self.manifest.is_file():
            raise FileNotFoundError(self.manifest)

    def _load_manifest(self):
        checksums = {}

        with self.manifest.open("r", encoding="utf-8") as file:
            for line in file:
                parts = line.strip().split(maxsplit=1)

                if len(parts) != 2:
                    continue

                expected_hash, filename = parts
                checksums[filename.lstrip("*")] = expected_hash.lower()

        return checksums

    def verify_file(self, relative_path):
        """Verify one file against the official SHA-256 manifest."""
        relative_path = Path(relative_path)

        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Path must stay inside the dataset directory.")

        filename = relative_path.as_posix()
        checksums = self._load_manifest()

        if filename not in checksums:
            raise KeyError(f"File absent from SHA-256 manifest: {filename}")

        file_path = self.root / relative_path

        if not file_path.is_file():
            raise FileNotFoundError(file_path)

        digest = hashlib.sha256()

        with file_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        actual_hash = digest.hexdigest()
        expected_hash = checksums[filename]

        return {
            "file": filename,
            "expected": expected_hash,
            "actual": actual_hash,
            "valid": actual_hash == expected_hash,
        }

    def verify_files(self, relative_paths):
        """Verify several files and return their individual results."""
        return [self.verify_file(path) for path in relative_paths]
