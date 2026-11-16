"""Shape and size contracts for the ADR-08 CNN."""

import pytest
import torch

from ml.model import ECGResNet1D, parameter_count


def test_cnn_outputs_one_logit_per_superclass() -> None:
    model = ECGResNet1D()
    result = model(torch.zeros((2, 12, 1000)))

    assert result.shape == (2, 5)
    assert parameter_count(model) == 310_613
    assert parameter_count(model) <= 600_000


def test_cnn_rejects_wrong_input_contract() -> None:
    model = ECGResNet1D()

    with pytest.raises(ValueError, match="12, 1000"):
        model(torch.zeros((1, 12, 5000)))
