# splitaudio 使用说明

音频分段工具：从 MP3 文件中提取封面、生成 WAV/变速 MP3、检测副歌/主歌并裁剪、生成歌词 DOCX 文档。

## 功能

- **题1（普通难度）**：封面 PNG + 48kHz 24bit WAV + 0.8x/1.2x 变速 MP3 + 歌词 DOCX
- **题2（挑战难度）**：原始 MP3 + 主歌裁剪 + 副歌高光裁剪 + 歌词 DOCX
- 支持一次运行产出全部交付物
- 跨平台：Windows / macOS / Linux 均可运行

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.10+ | 必需 |
| ffmpeg | 任意 | 必需（音频处理） |
| numpy | ≥1.24 | 自动安装 |
| python-docx | ≥1.0 | 自动安装 |

## 安装步骤

### 1. 安装 ffmpeg

**Windows:**
```powershell
# 方法1: winget（推荐）
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements

# 方法2: scoop
scoop install ffmpeg

# 方法3: choco
choco install ffmpeg

# 安装后重启终端，验证：
ffmpeg -version
```

**macOS:**
```bash
# 方法1: Homebrew（推荐）
brew install ffmpeg

# 方法2: MacPorts
sudo port install ffmpeg

# 验证：
ffmpeg -version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install ffmpeg

# 验证：
ffmpeg -version
```

**Linux (CentOS/RHEL/Fedora):**
```bash
# Fedora
sudo dnf install ffmpeg

# CentOS/RHEL（需启用 RPM Fusion）
sudo dnf install epel-release
sudo dnf install --enablerepo=rpmfusion-free-release ffmpeg
```

### 2. 安装 splitaudio

```bash

cd splitaudio

# 安装（推荐 editable 模式）
pip install -e .

# 或带 ffmpeg 兜底（imageio-ffmpeg 内嵌 ffmpeg 二进制）
pip install -e ".[fallback]"
```

## 使用方法

### 基本用法

```bash
# 一次运行产出两题全部交付物
splitaudio <文件夹路径>

# 示例
splitaudio ~/user/documents/test
splitaudio /path/to/music
```

### 指定任务

```bash
# 只跑题1（封面 + WAV + 变速 + 歌词）
splitaudio --task 1 <文件夹路径>

# 只跑题2（原始 + 主歌 + 副歌 + 歌词）
splitaudio --task 2 <文件夹路径>

# 两题全跑（默认）
splitaudio --task all <文件夹路径>
```

### 自定义输出目录

```bash
# 默认输出到 <文件夹路径>/output/
splitaudio <文件夹路径>

# 指定输出目录
splitaudio --output /path/to/output <文件夹路径>
```

### 调试模式

```bash
# 查看详细日志（包含 ffmpeg 命令）
splitaudio -v <文件夹路径>
```

### Python 模块方式

```bash
python -m splitaudio <文件夹路径>
python -m splitaudio --task 1 --output /tmp/out <文件夹路径>
```

### 查看版本和帮助

```bash
splitaudio --version
splitaudio --help
```

## 输出结构

```
output/
├── cover/                     # ── 题1 ──
│   ├── 歌曲A.png              # 封面图片（从 ID3 内嵌封面提取）
│   ├── 歌曲B.png
│   └── 歌曲C.png
├── lyrics/                    # ── 题1 + 2 ──
│   ├── 歌曲A.docx             # 歌词文档（宋体中文字体）
│   ├── 歌曲B.docx
│   └── 歌曲C.docx
└── audio/
    ├── wav/                   # ── 题1 ──  48kHz 24bit
    │   ├── 歌曲A.wav
    │   ├── 歌曲B.wav
    │   └── 歌曲C.wav
    ├── speed/                 # ── 题1 ──  变速
    │   ├── 歌曲A_0.8x.mp3    # 0.8 倍速
    │   ├── 歌曲A_1.2x.mp3    # 1.2 倍速
    │   └── ...
    ├── original/              # ── 题2 ──  原始音频（比特级复制）
    │   ├── 歌曲A.mp3
    │   └── ...
    ├── verse/                 # ── 题2 ──  主歌片段（15-25s）
    │   ├── 歌曲A_verse.mp3
    │   └── ...
    └── chorus/                # ── 题2 ──  副歌高光（15-25s）
        ├── 歌曲A_chorus.mp3
        └── ...
```

## 跨平台验证

本工具已在以下平台通过 CI 自动测试：

| 平台 | Python 版本 | 状态 |
|------|-------------|------|
| Ubuntu 24.04 (Linux) | 3.10, 3.12 | ✅ |
| Windows Server 2022 | 3.10, 3.12 | ✅ |
| macOS (Apple Silicon) | 3.10, 3.12 | ✅ |

## CLI 功能完整列表

| 命令 | 功能 | 退出码 |
|------|------|--------|
| `splitaudio <FOLDER>` | 运行两题全部任务 | 0=成功, 4=部分失败 |
| `splitaudio --task 1 <FOLDER>` | 仅题1（封面+WAV+变速+歌词） | 0=成功 |
| `splitaudio --task 2 <FOLDER>` | 仅题2（原始+主歌+副歌+歌词） | 0=成功 |
| `splitaudio --output <PATH> <FOLDER>` | 自定义输出目录 | 0=成功 |
| `splitaudio -v <FOLDER>` | 详细日志模式 | 0=成功 |
| `splitaudio --version` | 显示版本号 | 0 |
| `splitaudio --help` | 显示帮助信息 | 0 |
| `python -m splitaudio <FOLDER>` | 模块入口（等效 CLI） | 0=成功 |

### 错误处理

| 场景 | 退出码 | 说明 |
|------|--------|------|
| 目录不存在 | 2 | 输入路径不存在 |
| 不是目录 | 2 | 输入路径是文件而非目录 |
| 无音频文件 | 2 | 目录中未找到支持的音频格式 |
| ffmpeg 缺失 | 3 | 系统未安装 ffmpeg |
| 部分文件失败 | 4 | 部分音频处理出错 |

### 支持的音频格式

`.mp3` `.m4a` `.flac` `.wav` `.ogg` `.aac` `.wma` `.opus`

## 核心算法

副歌/主歌检测采用「能量 + 亮度 + 重复度 + 人声占比」四特征投票 + 位置先验：

1. **能量（RMS）**：副歌统计上更响
2. **亮度（谱质心）**：副歌更亮（ISMIR'13）
3. **重复度（chroma Pearson SSM）**：副歌是最重复的段（Bartsch/Goto）
4. **人声占比**：主歌定位辅助

降级链：L0（全特征）→ L1（去重复度）→ L2（Suno 结构先验）→ L3（跳过）

## 技术栈

- Python 3.10+ / numpy / python-docx
- 外部 ffmpeg（音频处理）
- GitHub Actions（跨平台 CI）
- 零重型依赖（不用 ASR/DL）

## 测试

```bash
# 单元测试（不依赖 ffmpeg，毫秒级）
python -m pytest tests/test_naming.py tests/test_lyrics.py tests/test_analysis.py -v

# 集成测试（真实端到端，需要 ffmpeg 和测试音频）
python -m pytest tests/test_integration.py -m integration -v

# 全部测试
python -m pytest tests/ -v
```

## 已知限制

1. **副歌检测精度**：基于信号处理启发式，对非标准结构歌曲可能偏差 ±3-5s
2. **主歌检测**：依赖能量跳变检测，对能量变化平缓的歌曲可能不够精确
3. **WAV 输出**：24bit 为处理容器位深，源为有损 mp3，不代表原始录音精度

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 2 | 用法/输入错误 |
| 3 | ffmpeg 缺失 |
| 4 | 部分文件失败 |

## License

Internal use only.
