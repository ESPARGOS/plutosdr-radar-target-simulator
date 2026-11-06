"""Check that response analysis removes only gain and delay, not ripple."""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analyze_wideband import residual_response

f = np.linspace(-27.5e6, 27.5e6, 176)
ripple = 0.7 * np.cos(2 * np.pi * f / 55e6)
phase_ripple = 0.08 * np.cos(2 * np.pi * f / 55e6)
h = np.array(
    [
        a
        * 10 ** (ripple / 20)
        * np.exp(1j * (offset - 2 * np.pi * f * delay + phase_ripple))
        for a, offset, delay in [(2, 0.7, 1e-6), (0.1, -0.2, 1.1e-6)]
    ]
)
gain, phase, delay = residual_response(f, h)
np.testing.assert_allclose(gain, np.tile(ripple - ripple.mean(), (2, 1)), atol=1e-10)
np.testing.assert_allclose(
    phase, np.tile(phase_ripple - phase_ripple.mean(), (2, 1)), atol=1e-10
)
np.testing.assert_allclose(delay, [1e-6, 1.1e-6], atol=1e-15)
gain2, phase2, delay2 = residual_response(f, h, 1e-6)
np.testing.assert_allclose(gain2, gain, atol=1e-10)
np.testing.assert_allclose(phase2, phase, atol=1e-10)
np.testing.assert_allclose(delay2, delay, atol=1e-15)
h_late = h * np.exp(-2j * np.pi * f * 4e-6)
gain3, phase3, delay3 = residual_response(f, h_late, 5e-6)
np.testing.assert_allclose(gain3, gain, atol=1e-10)
np.testing.assert_allclose(phase3, phase, atol=1e-10)
np.testing.assert_allclose(delay3, delay + 4e-6, atol=1e-15)
print(
    "PASS: removes constant gain and linear phase while preserving amplitude and phase ripple"
)
