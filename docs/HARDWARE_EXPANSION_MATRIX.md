# Hardware expansion matrix — evidence status

The real board is not available, so this repository contains **no production adapter** for a
camera, microphone, ToF/ultrasonic sensor, current sensor, or motor driver, and none will be added
on speculation.

## The blocking fact

**The board is not in hand, so the competition-board revision and every proposed electrical
integration remain unverified.**

Searches performed across the whole checkout:

- no schematic, pinout table, connector designator, or expansion-header document is stored in the
  repository;
- `note_TESA/คู่มือเทคนิคผู้เข้าแข่งขัน-TESAIoT2026.md` §2 lists on-board components only — dual
  core, BMI270, magnetometer, temperature/humidity, pressure, a 4.3" LVGL touchscreen, I2S with a
  TLV320DAC3100 codec, OPTIGA Trust M, Wi-Fi/BLE/USB-serial — and assigns **no pin, no header, and
  no voltage rail** to any expansion;
- the current [Infineon user guide](https://www.infineon.com/assets/row/public/documents/30/44/infineon-kit-pse84-ai-user-guide-usermanual-en.pdf)
  does document schematics, digital/analog expansion headers, an I2C connector, and 1.8 V / 3.3 V
  peripheral domains. These are candidate interfaces, not proof of the exact competition-board
  revision or of a working CargoShield adapter;
- the Infineon product page, user guide, and Zephyr board page list TrustZone-M and the SoC secure
  enclave but do not list a discrete OPTIGA. That absence does not prove the competition-board
  variant lacks one; Secure Edge milestone M1 must confirm the actual root of trust;
- the deleted `important_notes/TESAIoT_Hardware_and_NavShield_Specs.md` (recovered from HEAD for
  this audit) documents the same on-board sensors and likewise contains no pinout;
- no I2C, SPI, or GPIO expansion bus is documented anywhere in the checkout.

The project's own rule is that no purchasing recommendation or integration claim is valid until
the actual board revision, connector mapping, voltage/current budget, driver, and bench behaviour
are verified. Therefore every row below remains **unsupported in CargoShield**, even where the
official guide identifies a possible interface.

## Matrix

| Candidate module | Intended value | Board connector / bus | Voltage / current | Driver or library | Expected data rate | Compute / power effect | Can the board/NPU process it? | Evidence source | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kit camera | visual obstacle detection | current guide: 0.3 MP USB camera over USB-C; pre-rev-*A kits used OV7675 DVP | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | Infineon user guide; this repo has no camera driver/integration and `vision` is disabled | **unsupported — no integration evidence** |
| On-board analog/digital microphones | acoustic fault detection | on-board sensor subsystem | board-native, exact operating setup **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | Infineon user guide; this repo has no microphone ingest and `audio` is disabled | **unsupported — no integration evidence** |
| ToF / ultrasonic rangefinder | real obstacle distance | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; obstacle distance is an operator input today | **unsupported — no pinout evidence** |
| Current / power sensor | motor load and wear monitoring | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo | **unsupported — no pinout evidence** |
| Motor driver | actual locomotion | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; `actuator-config` in the installed profile is an **LED test pane** | **unsupported — no pinout evidence** |

## The one adjacent fact that *is* verified

The on-board ADC potentiometer channels are **0–1800 mV** (`pot1Mv`…`pot4Mv`, from the installed
Bitstream Studio 0.1.9 sensor catalog, version `2026-07-13`). Any future analog expansion would
have to fit that rail. **The connector that would carry it is undocumented**, so this narrows a
future option without authorising one.

## What would unblock this

Confirm the actual competition-board revision, then map each selected module to the official
connector and verify voltage, current, driver, sampling, and failure behaviour on the bench.
Secure Edge milestone M1 must separately confirm whether the root of trust is a discrete OPTIGA
Trust M or the SoC secure enclave.
