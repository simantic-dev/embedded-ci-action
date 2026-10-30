# embedded-ci-action
GitHub Action for submitting firmware .elf files to Simantic for simulation

## Usage

```yaml
on: [push, pull_request]

jobs:
  simulate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Installs the toolchains simantic.json calls for, cached between runs.
      - uses: simantic-dev/embedded-ci-action/setup@main

      - run: make -j"$(nproc)"

      - uses: simantic-dev/embedded-ci-action@main
        with:
          elf-path: build/firmware.elf
          api-url: https://run.simantic.dev
```

The result shows on the Simantic dashboard's Embedded CI tab.

## simantic.json

The project file in the repository root, the same one the Simantic PR
reviewer reads. `mcu` is the only required key:

```json
{
  "$schema": "https://simantic.com/schema/simantic.json",
  "mcu": "STM32F401RE"
}
```

`toolchain` pins versions, as prefixes (`14.3` is `14.3.rel1`, `2.1` the
newest `2.1.x`):

```json
{
  "mcu": "RP2040",
  "toolchain": { "arm-gnu": "14.3", "pico-sdk": "2.1" }
}
```

A project in a subfolder passes `config: path/to/simantic.json` to both steps.

## The setup step

`simantic-dev/embedded-ci-action/setup` installs, and caches with
`actions/cache`:

| Toolchain | When | Default | After it |
| --- | --- | --- | --- |
| Arm GNU Toolchain (`arm-none-eabi-gcc`) | an STM32 or RP2 MCU, or `toolchain.arm-gnu` | 14.3.rel1 | its `bin/` is on `PATH` |
| pico-sdk, with tinyusb and picotool | an RP2 MCU, `build.system: pico-sdk`, or `toolchain.pico-sdk` | 2.1.1 | `PICO_SDK_PATH`, `picotool_ROOT`, `picotool_DIR` |

The defaults are the versions the PR reviewer builds with. Without a
`toolchain`, the build system and then the MCU decide. Naming any toolchain
installs only the ones named (and Arm GNU with the pico-sdk). Zephyr and
ESP-IDF are not installed: use `zephyrproject-rtos/action-zephyr` or
`espressif/esp-idf-ci-action` before your build. It runs on Linux and macOS
runners.

The first run downloads (Arm GNU is about 150 MB); later runs restore from
the cache. GitHub keeps 10 GB of cache per repository and drops an entry no
run has used for 7 days.

Leave the step out to install toolchains yourself.

## simantic.yml (deprecated)

The older flat file still works, with a warning: `mcu_model` is the MCU, and
`trigger: push` (the default) or `trigger: pull_request` skips simulation on
the other event. With simantic.json, choose when CI runs with the workflow's
`on:`.
