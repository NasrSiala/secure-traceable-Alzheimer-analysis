import unittest

from ai_data.ptbxl.dataset import PTBXLDataLoader


class TestPTBXLDataLoader(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.loader = PTBXLDataLoader()
        cls.metadata = cls.loader.load_metadata()
        cls.splits = cls.loader.get_split()

    def test_metadata_count(self):
        self.assertEqual(len(self.metadata), 21799)

    def test_official_split_sizes(self):
        self.assertEqual(len(self.splits["train"]), 17418)
        self.assertEqual(len(self.splits["validation"]), 2183)
        self.assertEqual(len(self.splits["test"]), 2198)

    def test_patient_disjoint_splits(self):
        train = set(self.splits["train"]["patient_id"])
        validation = set(self.splits["validation"]["patient_id"])
        test = set(self.splits["test"]["patient_id"])

        self.assertFalse(train & validation)
        self.assertFalse(train & test)
        self.assertFalse(validation & test)

    def test_ecg_loading(self):
        ecg = self.loader.load_ecg(1)

        self.assertEqual(ecg["signal"].shape, (5000, 12))
        self.assertEqual(ecg["sampling_rate"], 500)
        self.assertEqual(len(ecg["leads"]), 12)
        self.assertTrue((set(ecg["units"]) == {"mV"}))

    def test_invalid_ecg_id(self):
        with self.assertRaises(KeyError):
            self.loader.load_ecg(-1)


if __name__ == "__main__":
    unittest.main()
