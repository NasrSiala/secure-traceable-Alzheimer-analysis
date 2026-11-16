"""SHA-256 integrity verification for PTB-XL files."""

from pathlib import Path

from saam.hashing import file_hash


class PTBXLIntegrityChecker:

    def __init__(self, dataset_root):
        self.root = Path(dataset_root)
        self.manifest = self.root / "SHA256SUMS.txt"

        if not self.manifest.is_file():
            raise FileNotFoundError(self.manifest)

        self._checksums = self._load_manifest()

    def _load_manifest(self):
        checksums = {}

        with self.manifest.open("r", encoding="utf-8") as file:
            for line in file:
                entry = line.strip()
                if not entry:
                    continue

                parts = entry.split(maxsplit=1)
                if len(parts) != 2:
                    raise ValueError("Malformed PTB-XL checksum manifest entry.")

                expected_hash, filename = parts
                filename = filename.lstrip("*")
                expected_hash = expected_hash.lower()
                if len(expected_hash) != 64 or any(
                    char not in "0123456789abcdef" for char in expected_hash
                ):
                    raise ValueError(
                        f"Invalid SHA-256 value in manifest for {filename}."
                    )
                if filename in checksums:
                    raise ValueError(f"Duplicate checksum entry: {filename}")
                checksums[filename] = expected_hash

        return checksums

    def verify_file(self, relative_path):
        """Verify one file against the official SHA-256 manifest."""
        relative_path = Path(relative_path)

        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Path must stay inside the dataset directory.")

        filename = relative_path.as_posix()
        if filename not in self._checksums:
            raise KeyError(f"File absent from SHA-256 manifest: {filename}")

        root = self.root.resolve()
        file_path = (root / relative_path).resolve()
        if not file_path.is_relative_to(root):
            raise ValueError("Path must stay inside the dataset directory.")

        if not file_path.is_file():
            raise FileNotFoundError(file_path)

        actual_hash = file_hash(file_path.read_bytes())
        expected_hash = self._checksums[filename]

        return {
            "file": filename,
            "expected": expected_hash,
            "actual": actual_hash,
            "valid": actual_hash == expected_hash,
        }

    def verify_files(self, relative_paths):
        """Verify several files and return their individual results."""
        return [self.verify_file(path) for path in relative_paths]
