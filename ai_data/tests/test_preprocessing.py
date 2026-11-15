import numpy as np
import pytest

from ai_data.ptbxl.preprocessing import ECGPreprocessor


@pytest.fixture
def preprocessor():
    return ECGPreprocessor()


@pytest.fixture
def valid_signal():
    rng = np.random.default_rng(42)
    return rng.normal(0, 0.2, size=(5000, 12))


def test_output_shape(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["signal"].shape == (5000, 12)


def test_output_dtype(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["signal"].dtype == np.float32


def test_output_is_finite(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert np.all(np.isfinite(result["signal"]))


def test_output_length_matches_input(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["signal"].shape[0] == valid_signal.shape[0]


def test_group_delay_metadata(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["group_delay_samples"] == 2266
    assert result["group_delay_seconds"] == pytest.approx(4.532)


def test_filter_metadata(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["filter_taps"] == 4533
    assert result["sampling_rate"] == 500
    assert result["leads"] == 12


def test_normalization_scale(preprocessor, valid_signal):
    result = preprocessor.preprocess(valid_signal)
    assert result["normalization_scale_mV"] == pytest.approx(
        np.max(np.abs(valid_signal))
    )


def test_invalid_dimensions(preprocessor):
    with pytest.raises(ValueError, match="2D array"):
        preprocessor.preprocess(np.ones(5000))


def test_wrong_number_of_leads(preprocessor):
    with pytest.raises(ValueError, match="12 leads"):
        preprocessor.preprocess(np.ones((5000, 8)))


def test_empty_signal(preprocessor):
    with pytest.raises(ValueError, match="cannot be empty"):
        preprocessor.preprocess(np.empty((0, 12)))


@pytest.mark.parametrize("invalid_value", [np.nan, np.inf, -np.inf])
def test_non_finite_values(preprocessor, invalid_value):
    signal = np.ones((5000, 12))
    signal[0, 0] = invalid_value

    with pytest.raises(ValueError, match="NaN or infinite"):
        preprocessor.preprocess(signal)


def test_zero_signal(preprocessor):
    with pytest.raises(ValueError, match="all-zero"):
        preprocessor.preprocess(np.zeros((5000, 12)))


def test_invalid_input_is_not_modified(preprocessor, valid_signal):
    original = valid_signal.copy()
    preprocessor.preprocess(valid_signal)
    np.testing.assert_array_equal(valid_signal, original)


def test_deterministic_output(preprocessor, valid_signal):
    first = preprocessor.preprocess(valid_signal)["signal"]
    second = preprocessor.preprocess(valid_signal)["signal"]

    np.testing.assert_array_equal(first, second)
