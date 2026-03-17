# AGENTS.md

## Repository Notes

- The active embedded firmware project lives in `Hardware/Mic-ESP32`.
- The PC-side audio hub project lives in `Software/pc_hub`.
- The firmware targets `ESP32-S3` and uses `ESP-IDF`, not Arduino.
- The local machine already has ESP-IDF `v5.5.3` installed through `eim-cli`.
- Device identity is split into:
  - `node_uuid`: derived from the ESP32-S3 STA MAC, used as the stable MQTT/backend key
  - `node_id`: human-readable display label from local secrets/config

## Local ESP-IDF Build

When building locally from Codex or a plain shell, do not assume `idf.py` is on `PATH`.

Use this environment:

- `IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf`
- `IDF_TOOLS_PATH=$HOME/.espressif/tools`
- `IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv`
- `ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011`

Preferred build command:

```sh
bash -lc '
export IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf
export IDF_TOOLS_PATH=$HOME/.espressif/tools
export IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv
export ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011
export PATH=$HOME/.espressif/tools/python/v5.5.3/venv/bin:$HOME/.espressif/tools/cmake/3.30.2/CMake.app/Contents/bin:$HOME/.espressif/tools/ninja/1.12.1:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/xtensa-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/riscv32-esp-elf/bin:$PATH
cd /Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32
$HOME/.espressif/tools/python/v5.5.3/venv/bin/python $IDF_PATH/tools/idf.py build
'
```

First-time target setup:

```sh
bash -lc '
export IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf
export IDF_TOOLS_PATH=$HOME/.espressif/tools
export IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv
export ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011
export PATH=$HOME/.espressif/tools/python/v5.5.3/venv/bin:$HOME/.espressif/tools/cmake/3.30.2/CMake.app/Contents/bin:$HOME/.espressif/tools/ninja/1.12.1:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin:$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/xtensa-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/bin:$HOME/.espressif/tools/riscv32-esp-elf/esp-14.2.0_20251107/riscv32-esp-elf/riscv32-esp-elf/bin:$PATH
cd /Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32
$HOME/.espressif/tools/python/v5.5.3/venv/bin/python $IDF_PATH/tools/idf.py set-target esp32s3 build
'
```

## Build Caveats

- In sandboxed execution, ESP-IDF configure/build may fail on macOS because `psutil` hits a `sysctl` permission boundary. If that happens, rerun the build unsandboxed.
- `ESP_ROM_ELF_DIR` must be set or the build emits `gen_gdbinit.py` warnings.
- `idf.py` from the stock `export.sh` path was not sufficient in this environment because `eim-cli` installed the Python venv in `~/.espressif/tools/python/v5.5.3/venv`.

## Build Outputs

After a successful build, expect:

- `Hardware/Mic-ESP32/build/mic_esp32_s3.bin`
- `Hardware/Mic-ESP32/build/bootloader/bootloader.bin`
- `Hardware/Mic-ESP32/build/partition_table/partition-table.bin`

## clangd

- The repository root contains `.clangd` that points clangd at `Hardware/Mic-ESP32/build/compile_commands.json`.
- VS Code settings are stored in `.vscode/settings.json` and pass:
  - `--compile-commands-dir=/Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32/build`
  - `--query-driver=/Users/tobiichieigetsu/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc`
- After rebuilding the firmware, clangd will pick up updated compile flags from the generated `compile_commands.json`.

## Identity Notes

- MQTT topics use `mic/<node_uuid>/...`, not `mic/<node_id>/...`.
- UDP packet headers include both `node_uuid` and `node_id`.
- `node_uuid` is not stored in secrets and is not persisted in NVS; it is derived on boot from the device MAC so it remains stable across reflashes.

## PC Hub Notes

- `Software/pc_hub` is a Python project intended to run with `/Users/tobiichieigetsu/Workspace/playground/.venv/bin/python`.
- Hub API endpoints:
  - `GET /nodes`
  - `POST /query/audio`
  - `POST /query/stt`
- Worker API endpoint:
  - `POST /transcribe`
- Query timebase is `PC receive time`, not the ESP32 device timestamp.
- The worker now uses `Qwen3-ASR` directly; the previous Whisper-based backends were removed.
- Main worker config:
  - `PC_HUB_ASR_MODEL`
  - `PC_HUB_ASR_LANGUAGE`
  - `PC_HUB_ASR_DEVICE_MAP`
  - `PC_HUB_ASR_DTYPE`
- `Software/pc_hub/pyproject.toml` explicitly packages `hub`, `shared`, and `worker`; `pip install -e .` should work from `Software/pc_hub`.
- `Software/pc_hub` now depends on `qwen-asr` directly instead of optional Whisper-family extras.
