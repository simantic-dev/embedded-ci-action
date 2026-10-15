# Simantic Simulate

Run your firmware on a simulated MCU on every push. No board, no runner setup. The Action uploads your
`.elf` to [Simantic Cloud Sim](https://cloud.simantic.com), waits for the run, prints the UART output, and
fails the job if the simulation fails or the output doesn't match what you expect.

## Quickstart

1. Create an API key (`smtc_…`) in the Simantic dashboard.
2. In your repo, open **Settings → Secrets and variables → Actions** and add it as `SIMANTIC_API_KEY`.
3. Add `.github/workflows/simantic.yml`:

```yaml
name: Simantic
on: [push, pull_request]

jobs:
  simulate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Build your firmware however you already do.
      - run: |
          sudo apt-get update && sudo apt-get install -y gcc-arm-none-eabi
          make

      - uses: simantic-dev/embedded-ci-action@v1
        with:
          elf: build/firmware.elf
          mcu: STM32F401RE
          api-key: ${{ secrets.SIMANTIC_API_KEY }}
          expect: 'ALL TESTS PASSED'
```

Push. The commit gets a check, and the job summary shows the UART output.

## Inputs

| input | required | default | |
|---|---|---|---|
| `elf` | yes | | Path to the built `.elf` |
| `mcu` | yes | | MCU to simulate. `curl -H "Authorization: Bearer $KEY" https://cloud.simantic.com/v1/mcus` lists them |
| `api-key` | yes | | Your `smtc_` key. Always pass it from a secret |
| `engine` | | API default (quartz) | Simulation engine, e.g. `pyrite` once the API version binds it |
| `simulated-seconds` | | `10` | Simulated time to run (max 60) |
| `expect` | | | Python regex the UART output must match for the step to pass |
| `uart-encoding` | | `ascii` | `ascii` or `hex` |
| `output-file` | | `simantic-output.txt` | Where the UART output is written, for `actions/upload-artifact` |
| `api-url` | | `https://cloud.simantic.com` | |

Outputs: `run-id` and `exit-code` (0 ok, 1 simulation failed, 2 usage error or unknown MCU).

## When the step fails

- The simulator exits nonzero (a fault, a bad image, an unknown MCU).
- `expect` is set and the UART output doesn't match it.
- The API refuses the request. The error from the API is printed as is (for example `mcu_not_supported`).

Each account can have 3 runs queued or running at once, and a run lasts at most 180 seconds of real time.

## Common builds

- **Zephyr:** `west build -b nucleo_f401re app`, then `elf: build/zephyr/zephyr.elf`
- **PlatformIO:** `pio run -e <env>`, then `elf: .pio/build/<env>/firmware.elf`
- **CMake / STM32CubeIDE:** point `elf` at the `.elf` your build already produces
