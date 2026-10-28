# Register interface

`radar_axi` is at physical address `0x43c00000`. Access with `build/rtsctl` on
Pluto (copied to `/tmp/rtsctl` by deployment). Writes go to shadow registers;
a stable mailbox plus request/acknowledge handshake applies all settings in
the RF clock domain. AXI address and data channels are accepted independently.

| Byte offset | Meaning |
| --- | --- |
| 0x00 | Signature `0x52545331` (`RTS1`) |
| 0x04 | Implementation version (current main build: `0x00010010`) |
| 0x08 | Number of targets: 4 |
| 0x0c | Maximum delay: 2047 samples |
| 0x10 | Write bit 0 to commit; bit 1 additionally restarts NCO phases |
| 0x14 | Bit 0: pending commit; bit 1: acknowledgment toggle |
| 0x18 | Sticky clipping flag, cleared on configuration/reset |
| 0x20 | Shadow target enable mask |
| 0x24 | Clock conditioner: write bit 0 to enable; read bits 0/1/2 = enabled/locked/running |
| 0x40 + 16*k | Target k delay in samples |
| 0x44 + 16*k | Target k signed phase increment (`f_D / fs * 2^32`) |
| 0x48 + 16*k | Target k unsigned Q1.15 amplitude (0–32767) |
| 0x4c + 16*k | Reserved shadow word |

`rtsctl status` returns JSON. `rtsctl mute` atomically clears the enable mask.
`rtsctl apply` reads a mask followed by four `delay increment gain` triples from
stdin, validates them and waits for acknowledgment. Do not access these physical
addresses unless the radar FPGA image is loaded.
