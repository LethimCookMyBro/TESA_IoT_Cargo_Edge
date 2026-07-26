# Hardware expansion matrix — evidence status

The real board is not available, so this repository contains **no production adapter** for a
camera, microphone, ToF/ultrasonic sensor, current sensor, or motor driver, and none will be added
on speculation.

## The blocking fact

**No board pinout, connector diagram, or voltage/current budget exists in this repository.**

Searches performed across the whole checkout:

- no schematic, pinout table, connector designator, or expansion-header document of any kind;
- `note_TESA/คู่มือเทคนิคผู้เข้าแข่งขัน-TESAIoT2026.md` §2 lists on-board components only — dual
  core, BMI270, magnetometer, temperature/humidity, pressure, a 4.3" LVGL touchscreen, I2S with a
  TLV320DAC3100 codec, OPTIGA Trust M, Wi-Fi/BLE/USB-serial — and assigns **no pin, no header, and
  no voltage rail** to any expansion;
- the deleted `important_notes/TESAIoT_Hardware_and_NavShield_Specs.md` (recovered from HEAD for
  this audit) documents the same on-board sensors and likewise contains no pinout;
- no I2C, SPI, or GPIO expansion bus is documented anywhere in the checkout.

The project's own rule is that no purchasing recommendation or integration claim is valid without
verified board pinout and connector evidence. That evidence does not exist here, so **every row
below is `unsupported — no pinout evidence`**, regardless of how plausible the module is.

## Matrix

| Candidate module | Intended value | Board connector / bus | Voltage / current | Driver or library | Expected data rate | Compute / power effect | Can the board/NPU process it? | Evidence source | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Camera (any) | visual obstacle detection | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; `vision` node family disabled in `release.modules.json` | **unsupported — no pinout evidence** |
| Microphone / MEMS mic | acoustic fault detection | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; board audio is a **TLV320DAC3100, output-only**; `audio` family disabled | **unsupported — no pinout evidence, and the on-board codec is a DAC** |
| ToF / ultrasonic rangefinder | real obstacle distance | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; obstacle distance is an operator input today | **unsupported — no pinout evidence** |
| Current / power sensor | motor load and wear monitoring | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo | **unsupported — no pinout evidence** |
| Motor driver | actual locomotion | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | **UNVERIFIED** | none in repo; `actuator-config` in the installed profile is an **LED test pane** | **unsupported — no pinout evidence** |

## The one adjacent fact that *is* verified

The on-board ADC potentiometer channels are **0–1800 mV** (`pot1Mv`…`pot4Mv`, from the installed
Bitstream Studio 0.1.9 sensor catalog, version `2026-07-13`). Any future analog expansion would
have to fit that rail. **The connector that would carry it is undocumented**, so this narrows a
future option without authorising one.

## What would unblock this

An official `KIT_PSE84_AI` pinout and connector document from the TESA AIoT platform sources. Until
one is in hand, this matrix stays as it is — a record of what is *not* known, which is the useful
thing to publish when the alternative is a plausible guess.
