import unittest

from ai_data.ptbxl.dataset import PTBXLDataLoader
from ai_data.ptbxl.diagnostics import (
    DIAGNOSTIC_CLASSES,
    summarize_diagnostics,
)


class TestPTBXLDiagnostics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = PTBXLDataLoader()
        cls.metadata = cls.loader.load_metadata()
        cls.statements = cls.loader.load_statements()
        cls.splits = cls.loader.get_split()

        cls.summary = summarize_diagnostics(
            cls.metadata,
            cls.statements,
            cls.splits,
        )

    def test_all_splits_are_present(self):
        self.assertEqual(
            set(self.summary["split"]),
            {"train", "validation", "test"},
        )

    def test_five_diagnostic_classes_are_present(self):
        self.assertEqual(
            set(self.summary["diagnostic_class"]),
            set(DIAGNOSTIC_CLASSES),
        )

    def test_each_ecg_is_counted_once_per_class(self):
        self.assertEqual(len(self.summary), 15)

        self.assertTrue(
            (self.summary["class_count"] <=
             self.summary["labeled_ecgs"]).all()
        )

    def test_labeled_and_unlabeled_counts(self):
        for split_name, split_metadata in self.splits.items():
            rows = self.summary[
                self.summary["split"] == split_name
            ]

            total = len(split_metadata)
            labeled = int(rows["labeled_ecgs"].iloc[0])
            unlabeled = int(rows["unlabeled_ecgs"].iloc[0])

            self.assertEqual(labeled + unlabeled, total)

    def test_no_negative_class_counts(self):
        self.assertTrue((self.summary["class_count"] >= 0).all())


if __name__ == "__main__":
    unittest.main()
