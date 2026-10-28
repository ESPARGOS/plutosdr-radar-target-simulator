#!/usr/bin/env python3
"""Record OFDM range/Doppler responses with one ESPARGOS TX and seven RX.
Uses pyespargos's existing calibrated IQ/accumulation APIs. Mutes both devices
on exit. Raw captures are saved for independent inspection.
"""

import argparse, json, os, queue, subprocess, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from control import Controller

p = argparse.ArgumentParser(description=__doc__)
p.add_argument(
    "--pyespargos",
    default=os.environ.get(
        "PYESPARGOS_PATH",
        str(Path(__file__).resolve().parents[2] / "ESPARGOS/pyespargos"),
    ),
)
p.add_argument(
    "--two-tone",
    action="store_true",
    help="Use coherent two-tone excitation for distortion measurements instead of OFDM",
)
p.add_argument(
    "--tone-bins",
    type=int,
    nargs=2,
    default=[13, 31],
    help="Two coherent tone bins at 78.125 kHz spacing; only used with --two-tone",
)
p.add_argument(
    "--occupied-bins",
    type=int,
    default=90,
    help="OFDM bins on each side of DC for single-transmitter broadband tests (1..120)",
)
p.add_argument(
    "--spectral-side",
    choices=("both", "positive", "negative"),
    default="both",
    help="One-sided broadband pilots separate mirror leakage from the transfer response",
)
p.add_argument(
    "--capture-pluto-input",
    action="store_true",
    help="Also capture raw Pluto ADC samples to assess input headroom",
)
p.add_argument(
    "--capture-pluto-dma",
    action="store_true",
    help="Lab snapshot via /tmp/radio-capture and the verified unused reserved DMA memory",
)
p.add_argument(
    "--adc-interval-seconds",
    type=float,
    default=0,
    help="Save repeated native ADC snapshots to inspect calibration settling; 0 disables",
)
p.add_argument(
    "--adc-samples",
    type=int,
    choices=(65536, 262144, 1048576),
    default=65536,
    help="Native ADC snapshot length; longer records lower the image-measurement floor",
)
p.add_argument(
    "--align-image-grid",
    action="store_true",
    help="Lab two-tone test: align the shared Pluto LO offset to half a receiver FFT bin so shifted images survive coherent accumulation",
)
p.add_argument(
    "--pluto-bist-tone",
    type=int,
    choices=(0, 1, 2, 3),
    help="Lab TX-only IQ image check: native transceiver tone index, requires source-off raw capture and no target scene",
)
p.add_argument(
    "--pluto-lo-offset-hz",
    type=int,
    default=0,
    help="Native TX-tone measurement only: offset Pluto from ESPARGOS to separate images from receiver spurs",
)
p.add_argument(
    "--rx-qec-decimation",
    type=int,
    choices=range(8),
    help="Lab-only RX correction-word update decimation, restored on exit; does not change RF sample filtering",
)
p.add_argument(
    "--http-close",
    action="store_true",
    help="Request fresh HTTP control connections for ESPARGOS transport diagnostics",
)
p.add_argument(
    "--raw-burst-chunks",
    type=int,
    choices=(0, 4, 16, 64),
    default=0,
    help="Unaveraged interval snapshots for off-grid spur measurements; 0 uses coherent accumulation",
)
p.add_argument("--baseline-seconds", type=float, default=2)
p.add_argument(
    "--accumulation-chunks",
    type=int,
    choices=(64, 128, 256, 512, 1024),
    default=1024,
    help="Shorter averages retain images despite residual LO drift",
)
p.add_argument(
    "--mimo",
    action="store_true",
    help="Use the established MIMO demo pilots and opposite corner transmitters",
)
p.add_argument(
    "--keep-radio-profile",
    action="store_true",
    help="Verify the sample rate/FIR state without changing them",
)
p.add_argument(
    "--expected-fir-enabled",
    type=int,
    choices=(0, 1),
    default=0,
    help="Expected FIR state with --keep-radio-profile",
)
p.add_argument("--pluto-sample-rate", type=float, default=60e6)
p.add_argument(
    "--pluto-bandwidth",
    type=int,
    help="Requested RX/TX analog bandwidth in Hz; actual values are recorded",
)
p.add_argument("--sample-rate", type=float, default=20e6)
p.add_argument(
    "--receiver-bandwidth-mhz",
    type=int,
    default=0,
    help="ESPARGOS analog RX filter for measurements; 0 keeps the MIMO demo open-filter configuration",
)
p.add_argument("--frequency", type=float, default=2380e6)
p.add_argument(
    "--source-off",
    action="store_true",
    help="Capture with ESPARGOS transmitters muted to test Pluto feedback",
)
p.add_argument(
    "--direct-loopback",
    action="store_true",
    help="Diagnostic FPGA source 10: bypass targets and tag echo with TX LO offset (requires diagnostic bitstream)",
)
p.add_argument("--host", default=os.environ.get("ESPARGOS_HOST", "192.168.1.100"))
p.add_argument("--pluto", default=os.environ.get("PLUTO_HOST", "192.168.4.1"))
p.add_argument("--seconds", type=float, default=4)
p.add_argument("--output", default="build/measurement.npz")
p.add_argument("--scene")
p.add_argument(
    "--espargos-only",
    action="store_true",
    help="Check receiver/transmitter capture without touching Pluto",
)
p.add_argument("--amplitude", type=float, default=0.08)
p.add_argument("--rx-gain", type=int, default=15)
p.add_argument("--pluto-rx-gain", type=float, default=20)
p.add_argument("--pluto-tx-attenuation", type=float, default=45)
a = p.parse_args()
if a.capture_pluto_input and a.capture_pluto_dma:
    p.error("Choose one Pluto ADC capture method")
if a.adc_interval_seconds and (a.adc_interval_seconds < 0.5 or a.espargos_only):
    p.error("ADC snapshot interval must be at least 0.5 s and requires Pluto")
if a.align_image_grid and (not a.two_tone or a.espargos_only or a.direct_loopback):
    p.error("Image alignment requires the normal Pluto two-tone test")
if a.pluto_bist_tone is not None and (
    not a.source_off or not a.raw_burst_chunks or a.scene or a.espargos_only
):
    p.error("Native TX tone requires source-off raw capture, Pluto, and no scene")
if a.pluto_lo_offset_hz and (
    a.pluto_bist_tone is None or abs(a.pluto_lo_offset_hz) > 3000000
):
    p.error("LO offset requires native TX-tone mode and must be within ±3 MHz")
if a.spectral_side != "both" and (a.mimo or a.two_tone):
    p.error("spectral-side applies only to broadband single-transmitter captures")
if a.raw_burst_chunks and a.mimo:
    p.error("Raw bursts currently support single-transmitter captures")
if not 0 < a.baseline_seconds <= 120:
    p.error("baseline-seconds must be in (0, 120]")
if not 0 <= a.receiver_bandwidth_mhz <= 54:
    p.error("Receiver bandwidth must be 0..54 MHz")
if a.receiver_bandwidth_mhz and not a.raw_burst_chunks:
    p.error(
        "Filtered receiver mode is for raw power measurements, not coherent calibrated captures"
    )
if not 1 <= a.occupied_bins <= 120:
    p.error("occupied-bins must be 1..120")
if len(set(a.tone_bins)) != 2 or any(not 1 <= b <= 110 for b in a.tone_bins):
    p.error("tone-bins must be two distinct bins in 1..110")
sys.path.insert(0, a.pyespargos)
if a.http_close:
    import http.client

    class ClosingHTTPConnection(http.client.HTTPConnection):
        def __init__(self, *args, **kwargs):
            kwargs["timeout"] = 15
            super().__init__(*args, **kwargs)

        def request(
            self, method, url, body=None, headers=None, *, encode_chunked=False
        ):
            headers = dict(headers or {})
            headers["Connection"] = "close"
            return super().request(
                method, url, body, headers, encode_chunked=encode_chunked
            )

    http.client.HTTPConnection = ClosingHTTPConnection
from espargos import Pool

if a.http_close:
    from espargos.board import Board

    original_fetch = Board._fetch

    def retry_read(self, path, data=None):
        for attempt in range(3):
            try:
                return original_fetch(self, path, data)
            except TimeoutError:
                # Setting the reference to an absolute mode is idempotent, including off.
                if (
                    (data is not None and path != "set_iq_reference")
                    or path in ("reboot", "factoryreset")
                    or attempt == 2
                ):
                    raise
                print(f"Retrying timed-out idempotent request: {path}", flush=True)

    Board._fetch = retry_read
from espargos.waveforms import IQSamples
import adi

ctrl = Controller(
    argparse.Namespace(
        demo=False,
        pluto=a.pluto,
        sample_rate=a.pluto_sample_rate,
        frequency=a.frequency,
    )
)
if a.espargos_only and a.scene:
    p.error("--scene requires Pluto")
if a.two_tone and a.mimo:
    p.error("--two-tone and --mimo are mutually exclusive")
if a.direct_loopback and (a.espargos_only or a.scene):
    p.error("--direct-loopback requires Pluto and supplies its own scene")
scene = json.loads(Path(a.scene).read_text()) if a.scene else {}
radio = None
radio_profile = {}
qec_decimation_saved = None


def dma_snapshot():
    env = os.environ.copy()
    env["SSHPASS"] = os.environ.get("PLUTO_PASSWORD", "analog")
    snapshot = subprocess.run(
        [
            "sshpass",
            "-e",
            "ssh",
            "-F",
            "/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            f"UserKnownHostsFile={ROOT}/build/known_hosts",
            f"root@{a.pluto}",
            f"/tmp/radio-capture {a.adc_samples}",
        ],
        capture_output=True,
        timeout=10,
        env=env,
        check=True,
    )
    words = np.frombuffer(snapshot.stdout, dtype="<u2").astype(np.int32)
    if len(words) != 2 * a.adc_samples:
        raise RuntimeError("Incomplete reserved-memory ADC snapshot")
    signed = ((words & 4095) ^ 2048) - 2048
    return signed[::2] + 1j * signed[1::2], json.loads(snapshot.stderr)


if not a.espargos_only:
    ctrl.mute()
    radio = adi.Pluto("ip:" + a.pluto)
    # pyadi's sample_rate setter installs/enables a 128-tap FIR. Use the
    # same FIR-bypassed hardware profile as firmware for latency comparisons.
    if a.keep_radio_profile:
        if (
            abs(
                radio._get_iio_attr("voltage0", "sampling_frequency", False)
                - a.pluto_sample_rate
            )
            > 100
            or radio._get_iio_attr("out", "voltage_filter_fir_en", False)
            != a.expected_fir_enabled
        ):
            raise RuntimeError(
                "Radio profile differs from the requested sample rate/FIR state"
            )
    else:
        radio._set_iio_attr("out", "voltage_filter_fir_en", False, 0)
        radio._set_iio_attr(
            "voltage0", "sampling_frequency", False, int(a.pluto_sample_rate)
        )
    if a.pluto_bandwidth is not None:
        radio.rx_rf_bandwidth = a.pluto_bandwidth
        radio.tx_rf_bandwidth = a.pluto_bandwidth
    radio.rx_lo = int(a.frequency) + a.pluto_lo_offset_hz
    radio.tx_lo = (
        int(a.frequency) + a.pluto_lo_offset_hz + (17 if a.direct_loopback else 0)
    )
    radio.gain_control_mode_chan0 = "manual"
    radio.rx_hardwaregain_chan0 = a.pluto_rx_gain
    radio.tx_hardwaregain_chan0 = -a.pluto_tx_attenuation
    radio_profile = {
        key: radio._ctrl.attrs[key].value for key in ("rx_path_rates", "tx_path_rates")
    }
    radio_profile["filter_control_registers"] = {
        str(addr): radio._ctrl.reg_read(addr) for addr in (2, 3)
    }
    radio_profile["interface_registers"] = {
        str(addr): radio._ctrl.reg_read(addr) for addr in (6, 7, 0x3B)
    }
    adc_device = radio._ctx.find_device("cf-ad9361-lpc")
    radio_profile["rx_iodelay"] = [
        adc_device.reg_read(0x80000800 + 4 * lane) for lane in range(13)
    ]
    radio_profile["tx_calibration_registers"] = {
        str(addr): radio._ctrl.reg_read(addr)
        for addr in (0x8E, 0x8F, 0x96, 0x97, 0xA0, 0xA1, 0xA7, 0xA9)
    }
    radio_profile.update(
        rx_rf_bandwidth=radio.rx_rf_bandwidth, tx_rf_bandwidth=radio.tx_rf_bandwidth
    )
    radio_profile["fir_enabled"] = radio._get_iio_attr(
        "out", "voltage_filter_fir_en", False
    )
    radio_profile.update(rx_lo=radio.rx_lo, tx_lo=radio.tx_lo)
    if a.direct_loopback:
        for address in (0x418, 0x458):
            radio._txdac.reg_write(address, 2)
        scene = {
            "targets": [
                {
                    "delay_us": 0,
                    "doppler_hz": radio.tx_lo - radio.rx_lo,
                    "gain_db": 0,
                    "enabled": True,
                }
            ]
        }
        if not 5 <= abs(scene["targets"][0]["doppler_hz"]) <= 35:
            raise RuntimeError("LO offset is outside the diagnostic Doppler band")
if a.mimo:
    sys.path.insert(0, str(Path(a.pyespargos) / "demos/iq/mimo-radar"))
    from mimo_processing import MIMOProcessor, pilots
else:
    if a.sample_rate != 20e6 and not (
        a.source_off and a.raw_burst_chunks and a.sample_rate in (40e6, 80e6)
    ):
        p.error(
            "Non-MIMO signals require 20 MSa/s; raw source-off noise tests also support 40/80 MSa/s"
        )
    rng = np.random.default_rng(3)
    bins = (
        np.array(a.tone_bins)
        if a.two_tone
        else np.r_[np.arange(-a.occupied_bins, 0), np.arange(1, a.occupied_bins + 1)]
    )
    if a.spectral_side != "both":
        bins = bins[bins > 0] if a.spectral_side == "positive" else bins[bins < 0]
    spectrum = np.zeros(1024, complex)
    spectrum[bins % 1024] = np.exp(1j * np.pi / 2 * rng.integers(0, 4, len(bins)))
    wave = np.fft.ifft(spectrum)
    wave /= max(abs(wave))
    reference = np.fft.fft(wave[:: round(80e6 / a.sample_rate)])
interval = 8192 if a.raw_burst_chunks else a.accumulation_chunks
fpga_status = {}
pluto_input = np.array([], dtype=complex)
pluto_input_error = None
adc_snapshots = []
adc_snapshot_times = []
q = queue.Queue(maxsize=4096)
frames = []
ticks = []
peaks = []
baseline = []
baseline_ticks = []
try:
    with Pool(a.host) as pool:
        pool.start_processing()
        tx = pool.tx
        antennas = list(pool.antennas)
        if a.mimo:
            processor = MIMOProcessor(
                pool.tx.positions.reshape(-1, 2), a.frequency, sample_rate=a.sample_rate
            )
            tx_antennas = [antennas[i] for i in processor.tx_indices]
            receivers = [antennas[i] for i in processor.rx_indices]
            reference = processor.pilots.sum(axis=0)
            bins = np.r_[np.arange(-120, 0), np.arange(1, 121)]
            interval = processor.interval_chunks
        else:
            tx_antennas = [antennas[0]]
            receivers = antennas[1:]
        board = pool.boards[0]
        indices = []
        for ant in receivers:
            row, col = board.revision.antenna_id_to_row_col(ant.antid)
            indices.append((0, row, col))
        index = tuple(np.array(indices).T)
        print(
            f"Configuring {a.frequency/1e6} MHz, {a.sample_rate/1e6} MSa/s RX, {len(tx_antennas)} OFDM transmitters",
            flush=True,
        )
        pool.configure(
            mode="iq_rx",
            frequency_hz=a.frequency,
            sample_rate_hz=a.sample_rate,
            rx_gain=a.rx_gain,
            output="antenna_r",
        )
        pool.iq.apply_config({"filter_bw_mhz": 0})
        transmitters = pool.select(antennas=tx_antennas)
        transmitters.configure(
            mode="iq_tx",
            frequency_hz=a.frequency,
            rf_gain={"a": 2 if a.mimo else 0, "b": 0},
            bandwidth_mhz=0,
            output="antenna_r",
        )
        with tx.update(samples=processor.tx_samples if a.mimo else 1024):
            for antenna, waveform in zip(
                tx_antennas, pilots(a.sample_rate) if a.mimo else [IQSamples(wave)]
            ):
                tx.signals.add(
                    waveform=waveform, amplitude=a.amplitude, antennas=[antenna]
                )
        print("Calibrating through the ESPARGOS reference", flush=True)
        pool.calibrate(tx_method="monitor")
        if a.receiver_bandwidth_mhz:
            # Grid acquisition needs the broadband reference. The subsequent raw PSD
            # averages powers per receiver and does not use the invalidated RF phase cal.
            pool.iq.apply_config({"filter_bw_mhz": a.receiver_bandwidth_mhz})
            print(
                f"Raw power capture: ESPARGOS RX filter {a.receiver_bandwidth_mhz} MHz",
                flush=True,
            )
        trigger = (
            {
                "mode": "interval",
                "burst_chunks": a.raw_burst_chunks,
                "interval_chunks": interval,
            }
            if a.raw_burst_chunks
            else {"mode": "accumulate", "vector_chunks": 1, "interval_chunks": interval}
        )
        pool.iq.apply_config({"trigger": trigger})

        def capture(cluster):
            iq = cluster.iq[index].copy()
            if np.all(np.isfinite(iq)):
                tick = (
                    cluster.chunk_index
                    if a.raw_burst_chunks
                    else cluster.source_chunk_start
                )
                try:
                    q.put_nowait((tick, iq, float(np.nanmax(cluster.adc_peak[index]))))
                except queue.Full:
                    pass

        if a.raw_burst_chunks:
            pool.iq.add_callback(capture)
        else:
            pool.iq.add_accumulation_callback(capture)
        if a.rx_qec_decimation is not None:
            if radio is None:
                raise ValueError("RX QEC experiment requires Pluto")
            qec_decimation_saved = radio._ctrl.reg_read(0x16F)
            radio._ctrl.reg_write(
                0x16F, (qec_decimation_saved & 31) | (a.rx_qec_decimation << 5)
            )
            radio_profile["qec_decimation_before"] = qec_decimation_saved
        if not a.source_off:
            transmitters.start_transmission()
        if a.align_image_grid:
            from analyze_raw_spurs import adc_offset

            alignment = []
            desired = a.sample_rate / len(reference) / 2
            for attempt in range(6):
                time.sleep(0.2)
                sample, _ = dma_snapshot()
                offset, ratio = adc_offset(
                    sample, a.pluto_sample_rate, bins * a.sample_rate / len(reference)
                )
                alignment.append(
                    dict(rx_lo=radio.rx_lo, offset_hz=offset, clock_ratio=ratio)
                )
                print(
                    f"Image-grid alignment: offset {offset:.2f} Hz, desired {desired:.2f} Hz",
                    flush=True,
                )
                if (
                    abs(offset - desired)
                    < a.sample_rate / (256 * a.accumulation_chunks) * 0.02
                ):
                    break
                if attempt == 5:
                    raise RuntimeError("Image-grid alignment did not converge")
                lo = radio.rx_lo + round((offset - desired) * ratio)
                radio.rx_lo = lo
                radio.tx_lo = lo
            radio_profile["image_grid_alignment"] = alignment
            radio_profile.update(rx_lo=radio.rx_lo, tx_lo=radio.tx_lo)
        print("Recording muted baseline", flush=True)
        time.sleep(0.3)
        while not q.empty():
            q.get_nowait()
        deadline = time.monotonic() + a.baseline_seconds
        while time.monotonic() < deadline:
            try:
                tick, iq, peak = q.get(timeout=0.5)
            except queue.Empty:
                continue
            baseline.append(iq)
            baseline_ticks.append(tick)
        if a.scene:
            ctrl.apply(scene)
            print("Recording programmed targets", flush=True)
        if a.pluto_bist_tone is not None:
            radio._ctrl.debug_attrs["bist_tone"].value = f"1 {a.pluto_bist_tone} 0 0"
            radio_profile["bist_tone_config"] = f"1 {a.pluto_bist_tone} 0 0"
            print("Recording native Pluto TX tone with all targets muted", flush=True)
        if a.direct_loopback:
            for address in (0x418, 0x458):
                radio._txdac.reg_write(address, 10)
            print(
                "Recording direct FPGA bypass with independent LO Doppler tag",
                flush=True,
            )
        time.sleep(0.3)
        if radio is not None:
            # UG-672 p25: overflow flags are latched; read twice to discard stale flags.
            # This supplements FPGA clipping; it does not measure raw ADC peak headroom.
            radio._ctrl.reg_read(0x5E)
            radio_profile["overflow_start"] = radio._ctrl.reg_read(0x5E)
            radio_profile["rx_power_config"] = radio._ctrl.reg_read(0x15C)
            radio_profile["rx_filter_power_start"] = radio._ctrl.reg_read(0x161)
        while not q.empty():
            q.get_nowait()
        deadline = time.monotonic() + a.seconds
        next_offset_check = time.monotonic()
        offset_tracking = []
        while time.monotonic() < deadline:
            if (
                a.align_image_grid or a.adc_interval_seconds
            ) and time.monotonic() >= next_offset_check:
                sample, _ = dma_snapshot()
                elapsed = a.seconds - (deadline - time.monotonic())
                if a.adc_interval_seconds:
                    adc_snapshots.append(sample)
                    adc_snapshot_times.append(elapsed)
                if a.align_image_grid:
                    offset, ratio = adc_offset(
                        sample,
                        a.pluto_sample_rate,
                        bins * a.sample_rate / len(reference),
                    )
                    offset_tracking.append(
                        dict(elapsed_s=elapsed, offset_hz=offset, clock_ratio=ratio)
                    )
                next_offset_check = time.monotonic() + (a.adc_interval_seconds or 2)
            try:
                tick, iq, peak = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if a.pluto_bist_tone is not None and peak >= 500:
                raise RuntimeError(
                    "Receiver overload during native TX tone; repeat with more TX attenuation"
                )
            ticks.append(tick)
            frames.append(iq)
            peaks.append(peak)
        if a.align_image_grid:
            radio_profile["image_grid_tracking"] = offset_tracking
        if radio is not None:
            radio_profile["overflow_end"] = radio._ctrl.reg_read(0x5E)
            radio_profile["rx_filter_power_end"] = radio._ctrl.reg_read(0x161)
            radio_profile["rx_tracking_registers"] = {
                str(addr): radio._ctrl.reg_read(addr) for addr in range(0x169, 0x178)
            }
        if a.capture_pluto_dma and radio is not None:
            pluto_input, radio_profile["adc_snapshot"] = dma_snapshot()
            print(
                "Pluto ADC snapshot: " + json.dumps(radio_profile["adc_snapshot"]),
                flush=True,
            )
        if a.capture_pluto_input and radio is not None:
            adc = radio._ctx.find_device("cf-ad9361-lpc")
            saved_adc = {
                addr: adc.reg_read(0x80000000 | addr) for addr in (0x400, 0x440)
            }
            try:
                radio.rx_buffer_size = 16384
                raw = radio.rx()

                # Format bypass leaves 12-bit two's-complement words in the low bits.
                def signed12(x):
                    return ((np.asarray(x, dtype=np.int32) & 4095) ^ 2048) - 2048

                pluto_input = signed12(raw.real) + 1j * signed12(raw.imag)
                print(
                    f"Pluto input peak {max(abs(pluto_input.real).max(),abs(pluto_input.imag).max())}/2048",
                    flush=True,
                )
            except Exception as error:
                pluto_input_error = repr(error)
                print(f"Optional Pluto ADC capture unavailable: {error}", flush=True)
            finally:
                radio.rx_destroy_buffer()
                for addr, value in saved_adc.items():
                    adc.reg_write(0x80000000 | addr, value)
        if not a.espargos_only:
            fpga_status = ctrl.call("status")
        unit = "raw chunks" if a.raw_burst_chunks else "coherent windows"
        print(
            f"Received {len(frames)} {unit}; peak ADC {max(peaks,default=0):.1f}/512",
            flush=True,
        )
finally:
    if qec_decimation_saved is not None and radio is not None:
        radio._ctrl.reg_write(
            0x16F, (radio._ctrl.reg_read(0x16F) & 31) | (qec_decimation_saved & 224)
        )
    if a.pluto_bist_tone is not None and radio is not None:
        radio.tx_hardwaregain_chan0 = -60
        radio._ctrl.debug_attrs["bist_tone"].value = "0 0 0 0"
    if not a.espargos_only:
        try:
            if a.direct_loopback and radio is not None:
                for address in (0x418, 0x458):
                    radio._txdac.reg_write(address, 2)
            ctrl.mute()
        finally:
            if radio is not None:
                radio.tx_hardwaregain_chan0 = -60
                if a.direct_loopback:
                    radio.tx_lo = radio.rx_lo
if len(frames) < 20:
    raise RuntimeError("Insufficient accumulated IQ")
path = Path(a.output)
path.parent.mkdir(parents=True, exist_ok=True)
np.savez_compressed(
    path,
    baseline=np.array(baseline),
    baseline_ticks=np.array(baseline_ticks),
    iq=np.array(frames),
    ticks=np.array(ticks),
    peaks=np.array(peaks),
    reference=reference,
    bins=bins,
    sample_rate=a.sample_rate,
    frequency=a.frequency,
    interval_chunks=interval,
    fpga_status=json.dumps(fpga_status),
    capture_settings=json.dumps(vars(a)),
    radio_profile=json.dumps(radio_profile),
    scene=json.dumps(scene),
    pluto_input=pluto_input,
    pluto_input_error=json.dumps(pluto_input_error),
    adc_snapshots=np.array(adc_snapshots),
    adc_snapshot_times=np.array(adc_snapshot_times),
)
print(f"Saved {path}", flush=True)
