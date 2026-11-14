import unittest

from ai_data.ptbxl.integrity import PTBXLIntegrityChecker


DATASET_ROOT = (
    r"C:\Users\ayedi\Datasets\PTB-XL"
    r"\ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
)


class TestPTBXLIntegrity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.checker = PTBXLIntegrityChecker(DATASET_ROOT)

    def test_metadata_integrity(self):
        result = self.checker.verify_file("ptbxl_database.csv")
        self.assertTrue(result["valid"])

    def test_ecg_header_integrity(self):
        result = self.checker.verify_file(
            "records500/00000/00001_hr.hea"
        )
        self.assertTrue(result["valid"])

    def test_ecg_signal_integrity(self):
        result = self.checker.verify_file(
            "records500/00000/00001_hr.dat"
        )
        self.assertTrue(result["valid"])

    def test_unknown_file_is_rejected(self):
        with self.assertRaises(KeyError):
            self.checker.verify_file("unknown_file.dat")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.checker.verify_file("../outside.txt")


if __name__ == "__main__":
    unittest.main()
