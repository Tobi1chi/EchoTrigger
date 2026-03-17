# AGENTS.md

English version: [AGENTS.md](AGENTS.md)

## 仓库说明

- 当前使用的嵌入式固件工程位于 `Hardware/Mic-ESP32`
- PC 侧音频 Hub 工程位于 `Software/pc_hub`
- 固件目标平台是 `ESP32-S3`，框架是 `ESP-IDF`，不是 Arduino
- 这台本机已经通过 `eim-cli` 安装了 `ESP-IDF v5.5.3`
- 设备身份分成两层：
  - `node_uuid`：由 ESP32-S3 的 STA MAC 派生，用作稳定 MQTT / 后端主键
  - `node_id`：来自本地 secrets / config 的可读显示名

## 本地 ESP-IDF 构建

在 Codex 或普通终端里本地构建时，不要假设 `idf.py` 已经在 `PATH` 中。

使用以下环境：

- `IDF_PATH=$HOME/.espressif/v5.5.3/esp-idf`
- `IDF_TOOLS_PATH=$HOME/.espressif/tools`
- `IDF_PYTHON_ENV_PATH=$HOME/.espressif/tools/python/v5.5.3/venv`
- `ESP_ROM_ELF_DIR=$HOME/.espressif/tools/esp-rom-elfs/20241011`

推荐构建命令：

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

首次设置 target：

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

## 构建注意事项

- 在沙箱环境下，ESP-IDF 的 configure/build 在 macOS 上可能因为 `psutil` 访问 `sysctl` 权限边界而失败。如果出现这种情况，需要在非沙箱环境重新执行
- 必须设置 `ESP_ROM_ELF_DIR`，否则构建过程中会出现 `gen_gdbinit.py` 警告
- 在这个环境里，仅靠 `export.sh` 暴露出来的 `idf.py` 路径还不够，因为 `eim-cli` 把 Python venv 安装到了 `~/.espressif/tools/python/v5.5.3/venv`

## 构建产物

成功构建后，期望产物：

- `Hardware/Mic-ESP32/build/mic_esp32_s3.bin`
- `Hardware/Mic-ESP32/build/bootloader/bootloader.bin`
- `Hardware/Mic-ESP32/build/partition_table/partition-table.bin`

## clangd

- 仓库根目录有 `.clangd`，指向 `Hardware/Mic-ESP32/build/compile_commands.json`
- VS Code 设置位于 `.vscode/settings.json`，并传入：
  - `--compile-commands-dir=/Users/tobiichieigetsu/Workspace/AI/Microphone/Hardware/Mic-ESP32/build`
  - `--query-driver=/Users/tobiichieigetsu/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20251107/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc`
- 固件重新构建后，clangd 会从生成的 `compile_commands.json` 读取最新编译参数

## 身份说明

- MQTT topic 使用 `mic/<node_uuid>/...`，不是 `mic/<node_id>/...`
- UDP 包头同时包含 `node_uuid` 和 `node_id`
- `node_uuid` 不存放在 secrets 中，也不持久化进 NVS；它在启动时由设备 MAC 派生，因此重刷后仍保持稳定

## PC Hub 说明

- `Software/pc_hub` 是一个 Python 工程，预期运行解释器是 `/Users/tobiichieigetsu/Workspace/playground/.venv/bin/python`
- Hub API：
  - `GET /nodes`
  - `POST /query/audio`
  - `POST /query/stt`
  - `GET /jobs/<job_id>`
- Worker API：
  - `POST /transcribe`
- 查询使用的时间轴是 `PC receive time`，不是 ESP32 的设备时间戳
- Worker 现在直接使用 `Qwen3-ASR`；之前的 Whisper 路线已经移除
- 主要的 Worker 配置：
  - `PC_HUB_ASR_MODEL`
  - `PC_HUB_ASR_LANGUAGE`
  - `PC_HUB_ASR_DEVICE_MAP`
  - `PC_HUB_ASR_DTYPE`
- `Software/pc_hub/pyproject.toml` 显式打包了 `hub`、`shared`、`worker`，从 `Software/pc_hub` 执行 `pip install -e .` 应该可用
- `Software/pc_hub` 现在直接依赖 `qwen-asr`，不再依赖可选的 Whisper 家族 extras
