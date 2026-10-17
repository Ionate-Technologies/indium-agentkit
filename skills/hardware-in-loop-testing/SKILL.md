---
name: hardware-in-loop-testing
description: "Build simulation and hardware-in-the-loop test suites for embedded firmware: instrument-timed stimulus, fault injection (brownout, bus disconnect, sensor noise), recovery checks, and guaranteed safe teardown, running first in Renode, QEMU, or a software model. Use when firmware behavior must be verified against simulated or real hardware signals. Not for writing the firmware itself (use the rtos-firmware-development skill)."
---

# Hardware-in-the-Loop Testing

Verify firmware against realistic signals and faults, and leave every rig in a
safe state no matter how a test ends. The stance is **simulation first, people
in control of energy**: tests run in a simulator or against simulated
instruments by default, and real hardware is energized only with an explicit
human go-ahead.

## When to use

- Testing how firmware reacts to sensor input, noise, bus loss, brownouts, or
  watchdog starvation.
- Building or extending a pytest-based HIL harness with programmable supplies,
  signal sources, DAQs, relays, or CAN interfaces.
- Moving a test from a bench script into a repeatable, simulated-first suite.

## When not to use

- Writing or fixing the firmware: use the `rtos-firmware-development` skill.
- A test that passes and fails on the same build: use the `flaky-test-triage`
  skill (rig timing is a common cause).
- Wiring the suite into a CI pipeline: use the `ci-pipeline` skill.

## Inputs to gather

Discover these from the repository and rig documentation before asking. Ask
only about what remains ambiguous and would change the result.

- The device under test (DUT): part numbers, supply voltage, absolute maximum
  ratings, brown-out threshold, and expected current, from the datasheets.
- The rig inventory: each instrument's model and role, and its programming
  manual. SCPI commands differ between models and vendors.
- VISA resource strings and other rig settings from the project's configuration
  files, never hard-coded in tests.
- Available simulation: Renode platform and script files, QEMU machine support,
  pyvisa-sim instrument definitions, or a software model of the DUT protocol.
- Pass criteria from the requirements (accuracy, recovery time, safe-state
  behavior). Do not invent limits; record missing ones as open questions.
- Safety arrangements: OVP and OCP limits, interlocks, the emergency stop, and
  who will be physically present.
- Test commands from `AGENTS.md`, package scripts, or the `Makefile`.

## Workflow

1. **Define each scenario.** Write the stimulus, the observation, and the pass
   criterion from the requirement, for example "after a 200 ms dip below the
   brown-out threshold, the DUT reports a brown-out reset and resumes its
   heartbeat within the requirement's limit (for example 2 s)".
2. **Choose the lowest tier that answers the question.**
   - Software model or simulated instruments (pyvisa-sim) to test the harness
     logic itself.
   - Renode or QEMU running the real firmware image, for control flow, protocol
     handling, and faults that can be modeled (a missing peripheral, injected
     sensor values, forced resets).
   - The real rig, only for analog behavior, real timing, and power faults, and
     only after step 6.
3. **Separate instrument roles.** Keep the DUT power supply (with OVP and OCP)
   distinct from the signal source (function generator, AWG, or DAC) and from
   measurement (DAQ, scope, logic analyzer). Wrap each in a small class whose
   commands are checked against that model's programming manual, and confirm
   the model with `*IDN?` before use.
4. **Let instruments do the timing.** For timed waveforms, dips, and noise,
   upload samples to the instrument's arbitrary-waveform or list mode and
   trigger it. Do not loop software-timed SCPI writes with `time.sleep`; host
   and VISA latency add milliseconds of jitter. Measure timing with hardware
   triggers or DUT timestamps when it matters; host `time.monotonic()` is
   coarse and only suits loose limits.
5. **Make teardown unconditional.** Instruments open in pytest fixtures whose
   teardown disables every output and closes the session, even when the test
   fails. Set limits and read them back before any output turns on. A crashed
   host or lost connection skips teardown, so the rig still needs its own
   protection: OVP and OCP, interlocks, and an emergency stop.
6. **Get the go-ahead for real hardware.** Before energizing a real rig, state
   the scenarios, voltages, currents, and durations, and wait for an explicit
   human approval for this session. A person must be physically present at the
   rig, or a remote emergency stop must be verified working, for every powered run.
7. **Run, then report** each scenario with its tier, measured values, and
   method of measurement.

## Reference: pytest fixture with guaranteed teardown (illustrative)

Defaults to simulated instruments. The SCPI strings follow a common pattern for
list-capable bench supplies; confirm each one in your instrument's manual.

```python
# tests/hil/conftest.py
import os

import pytest
import pyvisa

# Simulated instruments (pyvisa-sim) unless a person has approved a real rig run.
BACKEND = os.environ.get("HIL_VISA_BACKEND", "tests/hil/sim_instruments.yaml@sim")
PSU_RESOURCE = os.environ.get("HIL_PSU_RESOURCE", "TCPIP0::192.0.2.10::INSTR")  # placeholder

DUT_VOLTS = 3.3       # nominal supply, from the DUT datasheet
DUT_OVP_VOLTS = 3.6   # at or below the DUT absolute maximum rating
DUT_OCP_AMPS = 0.2    # expected draw plus margin, agreed with the hardware owner


class PowerSupply:
    """DUT supply. Generic SCPI: confirm every command in the model's programming manual."""

    def __init__(self, inst):
        self.inst = inst
        self.nominal_volts = None
        self.ovp_volts = None

    def configure(self, volts, ovp_volts, ocp_amps):
        self.inst.write("OUTP OFF")
        self.inst.write(f"VOLT:PROT {ovp_volts:.3f}")
        self.inst.write(f"CURR {ocp_amps:.3f}")
        self.inst.write("CURR:PROT:STAT ON")
        self.inst.write(f"VOLT {volts:.3f}")
        if abs(float(self.inst.query("VOLT:PROT?")) - ovp_volts) > 0.01:
            raise RuntimeError("OVP setting was not accepted; refusing to continue")
        self.nominal_volts = volts
        self.ovp_volts = ovp_volts

    def output(self, enabled):
        self.inst.write("OUTP ON" if enabled else "OUTP OFF")

    def run_list(self, volts, dwell_s):
        """Play a voltage sequence timed by the instrument's list mode, not by Python."""
        if self.ovp_volts is None or max(volts) >= self.ovp_volts:
            raise ValueError("list voltages must stay below the configured OVP limit")
        self.inst.write("LIST:VOLT " + ",".join(f"{v:.3f}" for v in volts))
        self.inst.write("LIST:DWEL " + ",".join(f"{d:.3f}" for d in dwell_s))
        self.inst.write("VOLT:MODE LIST")
        self.inst.write("TRIG:TRAN:SOUR BUS")
        self.inst.write("INIT:TRAN")
        self.inst.write("*TRG")


@pytest.fixture
def psu():
    if not BACKEND.endswith("@sim") and os.environ.get("HIL_HARDWARE_APPROVED") != "1":
        pytest.skip("real hardware needs explicit human approval for this session")
    rm = pyvisa.ResourceManager(BACKEND)
    inst = rm.open_resource(PSU_RESOURCE)
    inst.timeout = 5000  # milliseconds
    supply = PowerSupply(inst)
    try:
        supply.configure(DUT_VOLTS, DUT_OVP_VOLTS, DUT_OCP_AMPS)
        yield supply
    finally:
        try:
            supply.output(False)  # always runs, even when the test fails
        finally:
            inst.close()
            rm.close()
```

```python
# tests/hil/test_brownout.py
import time

BROWNOUT_VOLTS = 2.0    # below the DUT brown-out threshold, from the datasheet
RECOVERY_LIMIT_S = 2.0  # from the requirement; for example 2 s


def test_recovers_after_brownout(psu, dut):
    psu.output(True)
    dut.wait_for_heartbeat(timeout_s=5.0)

    psu.run_list(volts=[BROWNOUT_VOLTS, psu.nominal_volts], dwell_s=[0.2, 0.1])
    fault_at = time.monotonic()

    assert dut.wait_for_reset_reason("brownout", timeout_s=5.0)
    recovered_at = dut.wait_for_heartbeat(timeout_s=5.0)
    assert recovered_at - fault_at <= RECOVERY_LIMIT_S
```

`dut` is a project fixture that reads firmware telemetry (for example over a
UART) and returns `time.monotonic()` when a heartbeat arrives. Only the person
running the rig sets `HIL_HARDWARE_APPROVED`; an agent never sets it. A signal
source follows the same pattern: generate the samples in Python, upload them
once as an arbitrary waveform with amplitude, offset, and output limits that
keep the DUT input inside its rating, then trigger.

## Guardrails

- Never energize, reconfigure, or flash real hardware without explicit human
  approval for this session, and never without a person present or a verified
  remote emergency stop.
- Never exceed the DUT's absolute maximum ratings. Never disable OVP, OCP,
  interlocks, or the emergency stop, and never raise a limit to make a test pass.
- Keep mains-referenced equipment isolated from the DUT ground unless the rig
  design says otherwise; ask the hardware owner when unsure.
- Batteries, motors, heaters, and high-voltage rails need the hardware owner's
  sign-off for every scenario that drives them.
- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never weaken a pass criterion or skip a failing scenario to make a run green.

## Verification

Use the project's own commands. Run each check separately and report its real
result; never chain alternatives with `||`.

- Every Python file in the harness passes `python -m py_compile` and the
  project's lint.
- The suite passes against simulated instruments or the simulator, including a
  test that forces a failure and confirms teardown turned outputs off.
- For an approved real run: limits read back before output on, `OUTP?` (or the
  model's equivalent) reports off after teardown, and the measured values are
  recorded with the method used to measure them.

## Report

- **Tier:** simulation, simulated instruments, or real rig, and the approval for
  any real run.
- **Rig:** each instrument's role and `*IDN?` response, and the DUT firmware version.
- **Scenarios:** stimulus, pass criterion, measured result, and PASSED or FAILED.
- **Safety:** limits configured and read back, teardown confirmation.
- **Not verified:** scenarios not run, timing measured only on the host, and why.

## Optional delegation

- The `iot-embedded-auditor` subagent can review the firmware's fault and
  recovery handling before you design scenarios.
- The `test-writer` subagent can add simulation-tier tests for the harness.
