---
name: rtos-firmware-development
description: "Implement or change FreeRTOS or Zephyr firmware: tasks, ISRs, peripheral drivers (SPI, I2C, UART, CAN), DMA, watchdogs, and memory budgets, verified with cross-compiled builds, size checks, and static analysis. Use when writing or modifying embedded RTOS code for Cortex-M, RISC-V, or ESP32 targets. Not for test rigs (use the hardware-in-loop-testing skill). Never flashes a device without explicit approval."
---

# RTOS Firmware Development

Write firmware that meets its timing, memory, and interrupt rules on the actual
target, and prove it builds, fits, and passes static analysis before anything
touches hardware. The stance is **hardware-safe by default**: build and analyze
on the host; flashing, erasing, or reconfiguring a device needs explicit approval.

## When to use

- Adding or changing a task, ISR, queue, driver, or DMA transfer.
- Fixing priority inversion, stack overflow, missed deadlines, or watchdog resets.
- Porting a driver between FreeRTOS and Zephyr, or between MCU families.

## When not to use

- Building or running a hardware-in-the-loop or simulation rig: use the
  `hardware-in-loop-testing` skill.
- An independent firmware audit: delegate to the `iot-embedded-auditor` subagent.
- Secure boot, image signing, or other cryptography: use the
  `cryptographic-protocol-implementation` skill.
- A defect whose cause is unknown: use the `systematic-debugging` skill first.

## Inputs to gather

Discover these from the repository before asking. Ask only about what remains
ambiguous and would change the result.

- The exact MCU part and core. Cortex-M4F and Cortex-M7 differ in ways that
  matter here (the M7 usually has a data cache).
- RTOS and version: `FreeRTOSConfig.h`, or Zephyr `prj.conf`, Kconfig, and
  devicetree overlays.
- Interrupt configuration: `configPRIO_BITS`,
  `configMAX_SYSCALL_INTERRUPT_PRIORITY`,
  `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY`, and the NVIC priority grouping.
- Linker script, memory map, heap scheme (`heap_4.c`, static allocation), and
  the current size of the image.
- The HAL in use (STM32 HAL, nrfx, ESP-IDF, Zephyr drivers) and sibling drivers
  to copy conventions from.
- Timing requirements (periods, deadlines, worst-case latency) from the
  requirements or datasheets, not guesses.
- Build, size, and static analysis commands from `AGENTS.md`, CMake presets,
  the `Makefile`, or `west`.

## Workflow

1. **Orient.** Read the RTOS configuration, the linker script, and two sibling
   drivers. Note whether the core has a data cache, the tick rate, and how
   interrupt priorities are assigned.
2. **Design tasks.** For each task record its period or trigger, deadline,
   priority, stack size, and the resources it shares. Give shorter deadlines
   higher priority as a starting point. Protect shared peripherals with a mutex
   (which has priority inheritance), never a binary semaphore. Pass data through
   queues; signal events with direct-to-task notifications or semaphores.
3. **Keep ISRs short and legal.**
   - Call only `FromISR` APIs, then `portYIELD_FROM_ISR`; defer work to a task.
   - On Cortex-M, any ISR that calls a FreeRTOS API must have a logical priority
     at or below `configMAX_SYSCALL_INTERRUPT_PRIORITY`, which means a numeric
     priority value equal to or greater than it (higher numbers are less
     urgent). With the STM32 HAL, compare the unshifted value passed to
     `HAL_NVIC_SetPriority` against `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY`.
     With `configASSERT` defined, recent ports catch violations at run time.
   - Never take a mutex or block in an ISR.
4. **Make DMA safe.**
   - DMA buffers are static or global, never on a task stack.
   - On a core with a data cache enabled (for example Cortex-M7 parts such as
     STM32F7 and STM32H7), align buffers to 32 bytes and pad them to whole cache
     lines, clean the cache over a TX buffer before starting, and invalidate it
     over an RX buffer after completion, or place buffers in non-cacheable
     memory through the MPU. Cores without a data cache, such as the STM32F4's
     Cortex-M4, need none of this.
   - Wait for completion with a timeout. On timeout, abort the transfer, then
     drain any completion signal that raced the abort so the next cycle does not
     consume a stale one.
5. **Handle peripheral failure.** Recover a stuck I2C bus (clock SCL up to nine
   times while SDA is held low, then issue a STOP) when a slave can hang the
   bus. Check UART overrun and framing flags and use ring buffers with
   single-writer indices. Handle CAN error-passive and bus-off states explicitly.
6. **Supervise with the watchdog.** One monitor task refreshes the hardware
   watchdog only after every supervised task has checked in within its window
   (for example with event-group bits). Never refresh it from an ISR or the tick
   hook, which keeps it fed while tasks hang.
7. **Bound memory.** Set `configCHECK_FOR_STACK_OVERFLOW` to 2 and implement
   `vApplicationStackOverflowHook`. Measure each task with
   `uxTaskGetStackHighWaterMark` (words left at the low point) under worst-case
   load, and the heap with `xPortGetMinimumEverFreeHeapSize` for heap_4 and
   heap_5. `configASSERT` every handle and creation result.
8. **Build and analyze** (see Verification).
9. **Hardware runs need approval.** Ask before flashing, erasing, or resetting
   a device; then report exactly what was run.

## Reference (illustrative)

### FreeRTOS: SPI DMA read with a task notification

STM32F4 (Cortex-M4F, no data cache), FreeRTOS 10.4 or later, STM32 HAL. The
DMA stream interrupts that complete SPI1 transfers must follow the priority rule
in step 3, because the completion callback calls a `FromISR` API.

```c
#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"
#include "stm32f4xx_hal.h"

#define SENSOR_STACK_WORDS 512U          /* xTaskCreate takes words: 2048 bytes */
#define SENSOR_PRIORITY    (tskIDLE_PRIORITY + 3U)
#define SENSOR_PERIOD_MS   10U
#define SENSOR_XFER_LEN    6U

extern SPI_HandleTypeDef hspi1;          /* initialized by the HAL setup code */

static TaskHandle_t sensorTask;
static SemaphoreHandle_t spiMutex;       /* shared bus: a mutex gives priority inheritance */
static uint32_t overruns;
static uint32_t dmaTimeouts;

/* Static DMA buffers, never on a task stack. Read command per the sensor datasheet. */
static uint8_t txBuf[SENSOR_XFER_LEN] = { 0xE8U };
static uint8_t rxBuf[SENSOR_XFER_LEN];

void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi)
{
    if (hspi->Instance == SPI1) {
        BaseType_t woken = pdFALSE;
        vTaskNotifyGiveFromISR(sensorTask, &woken);
        portYIELD_FROM_ISR(woken);
    }
}

static void sensorTaskFn(void *arg)
{
    (void)arg;
    TickType_t lastWake = xTaskGetTickCount();

    for (;;) {
        if (xTaskDelayUntil(&lastWake, pdMS_TO_TICKS(SENSOR_PERIOD_MS)) == pdFALSE) {
            overruns++;                  /* the previous cycle ran past its period */
        }
        if (xSemaphoreTake(spiMutex, pdMS_TO_TICKS(5)) != pdTRUE) {
            continue;                    /* bus busy: skip this cycle, never block forever */
        }
        if (HAL_SPI_TransmitReceive_DMA(&hspi1, txBuf, rxBuf, SENSOR_XFER_LEN) == HAL_OK) {
            if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(2)) != 0U) {
                int16_t accelX = (int16_t)(((uint16_t)rxBuf[2] << 8) | rxBuf[1]);
                (void)accelX;            /* hand off through a queue in real code */
            } else {
                dmaTimeouts++;
                (void)HAL_SPI_Abort(&hspi1);
                (void)ulTaskNotifyTake(pdTRUE, 0); /* drain a completion that raced the abort */
            }
        }
        xSemaphoreGive(spiMutex);
    }
}

void sensorInit(void)
{
    spiMutex = xSemaphoreCreateMutex();
    configASSERT(spiMutex != NULL);

    BaseType_t created = xTaskCreate(sensorTaskFn, "sensor", SENSOR_STACK_WORDS, NULL,
                                     SENSOR_PRIORITY, &sensorTask);
    configASSERT(created == pdPASS);
}
```

Notes on the example:

- `pdMS_TO_TICKS` rounds down. At a 100 Hz tick, `pdMS_TO_TICKS(2)` is 0 and
  the wait never blocks; check every timeout against `configTICK_RATE_HZ`.
- If this task also uses stream buffers or another notifier, use a dedicated
  notification index (`ulTaskNotifyTakeIndexed`) or a binary semaphore created
  with `xSemaphoreCreateBinary`. `vSemaphoreCreateBinary` is deprecated.
- Kernels before 10.4 have `vTaskDelayUntil`, which returns nothing.
- ESP-IDF's FreeRTOS measures stack sizes and high-water marks in bytes, not
  words; check the port before sizing stacks.
- On a Cortex-M7 with the data cache on, declare 32-byte buffers with
  `__attribute__((aligned(32)))`, call `SCB_CleanDCache_by_Addr` on the TX
  buffer before starting, and `SCB_InvalidateDCache_by_Addr` on the RX buffer
  after the notification arrives.

### Zephyr equivalents

- Signaling: `k_sem_give` is safe from an ISR; the thread waits with
  `k_sem_take(&sem, K_MSEC(2))`. Use `k_poll` to wait on several events,
  `k_mutex` (priority inheritance) for shared resources, and `k_msgq` for data.
- Hardware comes from devicetree: get the bus with `SPI_DT_SPEC_GET` and
  transfer with `spi_transceive_dt`; enable drivers in `prj.conf`.
- Zero-latency interrupts must not call kernel APIs.
- Stacks and supervision: `CONFIG_HW_STACK_PROTECTION` or
  `CONFIG_STACK_SENTINEL`, `CONFIG_THREAD_ANALYZER` for usage, and the task
  watchdog subsystem (`CONFIG_TASK_WDT`) for per-thread supervision.

## Guardrails

- Never flash, erase, reset, or debug-attach to a device without explicit
  approval. Never change option bytes, enable read-out protection, or blow
  eFuses without written confirmation of the exact operation; some of these are
  permanent.
- Revert or delete only files you created or changed in this session, and say
  so. Never discard someone else's uncommitted work.
- Never weaken a check to make a build pass: no disabling `configASSERT`, stack
  overflow checking, warnings, or the watchdog.
- Every blocking call has a finite timeout chosen from the timing requirement.
- Do not change the linker script, clock tree, or interrupt priority scheme as a
  side effect of a driver change; raise it as a separate decision.

## Verification

Use the project's own commands. Run each check separately and report its real
result; never chain alternatives with `||`.

```bash
# Illustrative. Build and link to an ELF with the project's build, then size that ELF.
cmake --build build
arm-none-eabi-size build/firmware.elf

# Zephyr: west prints a memory usage table at link time.
west build -b <board> app
west build -t ram_report

# Static analysis; add MISRA checking if the project has licensed rule texts or a tool.
cppcheck --enable=warning,style,portability --inline-suppr -I include src
```

- The build succeeds with the project's warning flags and no new warnings.
- Size: `text + data` fits flash and `data + bss` plus heap and stacks fit RAM,
  with the margin the project requires. Compare with the size before the change.
- GCC's `-fstack-usage` output or the RTOS high-water marks show stack headroom
  for the changed tasks.
- Static analysis reports no new findings in the changed files.
- Host-side unit tests for driver logic pass, if the project has them.
- Anything run on hardware or in simulation is reported with its approval.

## Report

- **Target:** MCU, core, RTOS and version, toolchain.
- **Changes:** tasks and ISRs added or changed, with priority, period, stack
  size, and measured high-water mark where available.
- **Interrupts:** each ISR that calls the RTOS, with its numeric priority.
- **Memory:** flash and RAM use before and after.
- **Verification:** each command and its result.
- **Not verified:** hardware behavior, timing under load, and anything not run.

## Optional delegation

- Delegate an independent audit of priorities, ISR rules, DMA, and stack use to
  the `iot-embedded-auditor` subagent.
- Use the `hardware-in-loop-testing` skill to test the change in simulation or
  on an approved rig.
