"""ECG preprocessing for the PTB-XL CNN pipeline."""

from pathlib import Path

import numpy as np
import pandas as pd

from ai_data.ptbxl.fir_fixed_point import fir_fixed_point_reference


DEFAULT_COEFFICIENTS = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "fir_coefficients_q15.csv"
)

EXPECTED_LEADS = 12
DEFAULT_SAMPLING_RATE = 500


class ECGPreprocessor:
    """Prepare 12-lead ECG signals for CNN input."""

    def __init__(
        self,
        coefficients_path=DEFAULT_COEFFICIENTS,
        sampling_rate=DEFAULT_SAMPLING_RATE,
        expected_leads=EXPECTED_LEADS,
    ):
        self.sampling_rate = int(sampling_rate)
        self.expected_leads = int(expected_leads)

        if self.sampling_rate != 500:
            raise ValueError("This FIR configuration requires 500 Hz.")

        if self.expected_leads != 12:
            raise ValueError("PTB-XL preprocessing requires 12 leads.")

        coefficients_path = Path(coefficients_path)
        if not coefficients_path.is_file():
            raise FileNotFoundError(
                f"FIR coefficients not found: {coefficients_path}"
            )

        table = pd.read_csv(coefficients_path)

        required = {"coefficient_q15"}
        missing = required.difference(table.columns)
        if missing:
            raise ValueError(
                f"Missing FIR coefficient columns: {sorted(missing)}"
            )

        coefficients = table["coefficient_q15"].to_numpy()

        if coefficients.ndim != 1 or len(coefficients) == 0:
            raise ValueError("Invalid FIR coefficient array.")

        if not np.issubdtype(coefficients.dtype, np.integer):
            if not np.all(np.isfinite(coefficients)):
                raise ValueError("FIR coefficients contain invalid values.")
            if not np.all(coefficients == np.floor(coefficients)):
                raise ValueError("FIR coefficients must be integers.")

        if np.any(coefficients < -32768) or np.any(coefficients > 32767):
            raise ValueError("FIR coefficients must fit in int16.")

        self.coefficients_q15 = coefficients.astype(np.int16)
        self.group_delay = (len(self.coefficients_q15) - 1) // 2

        if (len(self.coefficients_q15) - 1) % 2 != 0:
            raise ValueError("FIR filter must have an integer group delay.")

    def preprocess(self, signal):
        """Filter, align, normalize and return a CNN-ready ECG."""
        signal = np.asarray(signal, dtype=np.float64)

        if signal.ndim != 2:
            raise ValueError("ECG signal must be a 2D array (samples, leads).")

        if signal.shape[0] == 0:
            raise ValueError("ECG signal cannot be empty.")

        if signal.shape[1] != self.expected_leads:
            raise ValueError(
                f"Expected {self.expected_leads} leads, "
                f"received {signal.shape[1]}."
            )

        if not np.all(np.isfinite(signal)):
            raise ValueError("ECG signal contains NaN or infinite values.")

        scale = float(np.max(np.abs(signal)))

        if scale == 0.0:
            raise ValueError("Cannot normalize an all-zero ECG signal.")

        # Global scaling preserves relative amplitudes between leads.
        quantized = np.rint(
            signal / scale * 32767.0
        ).astype(np.int16)

        # Reflect the signal at both boundaries to reduce zero-padding
        # artifacts while preserving the original Q1.15 FIR coefficients.
        delay = self.group_delay
        padded = np.pad(
            quantized,
            ((delay, delay), (0, 0)),
            mode="reflect",
        )

        filtered = np.column_stack([
            fir_fixed_point_reference(
                padded[:, lead],
                self.coefficients_q15,
            )
            for lead in range(self.expected_leads)
        ])

        # Remove the left reflection padding and compensate FIR delay.
        start = 2 * delay
        aligned = filtered[start:start + signal.shape[0], :]

        if aligned.shape != signal.shape:
            raise RuntimeError("Unexpected ECG output shape after FIR alignment.")

        # Convert Q1.15 output to a globally normalized float32 tensor.
        normalized = aligned.astype(np.float32) / 32768.0

        return {
            "signal": normalized,
            "sampling_rate": self.sampling_rate,
            "leads": self.expected_leads,
            "original_shape": tuple(signal.shape),
            "output_shape": tuple(normalized.shape),
            "normalization_scale_mV": scale,
            "filter_taps": len(self.coefficients_q15),
            "group_delay_samples": delay,
            "group_delay_seconds": delay / self.sampling_rate,
            "padding_mode": "reflect",
            "dtype": str(normalized.dtype),
        }
