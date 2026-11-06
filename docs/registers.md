# Register interface

`radar_axi` is at physical address `0x43c00000`. Use `rtsctl` on Pluto, or
access the registers through the shared control lock. Writes go to shadow
registers. A mailbox transfers a complete scene to the sample-clock domain,
and all four targets adopt it together. AXI address and data channels are
accepted independently.

| Byte offset | Meaning |
| --- | --- |
| 0x00 | Signature `0x52545331` (`RTS1`) |
| 0x04 | Interface version `0x00020002` |
| 0x08 | Number of targets: 4 |
| 0x0c | Maximum programmable delay: 12276 samples |
| 0x10 | Command: bit 0 commits a scene, bit 1 also restarts phase, bit 2 requests a live snapshot |
| 0x14 | Bit 0: command pending, bit 1: acknowledgment toggle |
| 0x18 | Sticky clipping flag, cleared when a scene takes effect or on reset |
| 0x20 | Shadow target enable mask |
| 0x24 | Clock conditioner: write bit 0 to enable, read bits 0/1/2 for enabled/locked/running |
| 0x28 | Fractional delay precision: 10 bits |
| 0x2c | Feature bits: bit 0 indicates FPGA motion |
| 0x40 + 16*k | Target k integer delay |
| 0x44 + 16*k | Target k signed phase increment (`f_D / fs × 2^32`) |
| 0x48 + 16*k | Target k unsigned Q1.15 amplitude (0–32767) |
| 0x4c + 16*k | Target k fractional delay in unsigned Q0.16 |
| 0x80 + 8*k | Low 32 bits of target k's signed 48-bit delay step |
| 0x84 + 8*k | High 16 bits of the delay step |
| 0xa0 | Bits 0–3: movement mask, 4–7: position edit mask, 8–11: velocity edit mask |
| 0xa4 | Upper movement boundary in whole samples |
| 0x100 + 16*k | Snapshot: integer delay, phase increment, amplitude and Q0.16 fraction in four consecutive words |

Here `k` runs from 0 to 3. The top ten fractional bits select the interpolation
coefficients. Motion integrates at higher precision, and a snapshot includes
six additional fractional position bits. The delay excludes the fixed hardware
latency. The maximum integer delay cannot have a nonzero fractional part.

For moving targets, set the delay step to `round(−f_D / f_carrier × 2^48)`.
Its magnitude must be less than half a sample per input sample. The movement
boundary must be between 1 and the maximum delay. The edit masks distinguish a
new position or velocity from an unrelated gain or enable change. Clear both
edit masks when pausing a trajectory with mute.

Wait until the pending bit clears before issuing another command. Request a
snapshot with command bit 2, wait for acknowledgment, then read all snapshot
words. They remain stable until the next snapshot request. Reading shadow words
alone does not give the current position or direction of a moving target.

`rtsctl status` requests a snapshot and returns JSON. `rtsctl mute` pauses the
targets at their current positions and clears the enable mask. `rtsctl apply`
reads the following text from stdin:

```text
fractional
1
100 456 16384 32768
0 0 0 0
0 0 0 0
0 0 0 0
```

This enables the first target at 100.5 samples of added delay. The four values
on each target row are integer delay, phase increment, gain and fraction.
Encode a negative phase increment as its unsigned 32-bit representation.
The older mask-plus-four-triples format is also accepted and selects integer
delays. Command-line scene updates disable movement. The HTTP API adds movement
settings to the same scene format, as described in [architecture.md](architecture.md).
