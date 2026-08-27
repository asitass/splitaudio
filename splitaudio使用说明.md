# splitaudio

从音频文件中提取封面、歌词、音频变体，并检测副歌/主歌片段。

## 环境要求

- **Python 3.10+**
- **ffmpeg**（必须在 PATH 中）

### 安装 ffmpeg

```bash
# Linux (Ubuntu/Debian)
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
winget install ffmpeg
```

或安装内置的备用方案：

```bash
pip install ".[fallback]"
```

## 安装

```bash
cd splitaudio
pip install -e .
```

## 使用方法

```bash
# 运行全部任务（封面 + wav + 变速 + 歌词 + 主歌/副歌裁剪）
splitaudio /path/to/test

# 仅运行任务1（封面、wav、变速、歌词）
splitaudio --task 1 /path/to/test

# 仅运行任务2（原始音频、主歌、副歌裁剪）
splitaudio --task 2 /path/to/test

# 指定输出目录
splitaudio --output /path/to/output /path/to/test

# 调试模式（详细日志）
splitaudio -v /path/to/test
```

或作为模块运行：

```bash
python -m splitaudio /path/to/test
```

## 输出结构

```
output/
├── cover/                     # 任务1：封面图片（PNG）
│   └── <歌名>.png ×3
├── lyrics/                    # 任务1+2：歌词（DOCX）
│   └── <歌名>.docx ×3
└── audio/
    ├── wav/                   # 任务1：48kHz 24bit WAV
    │   └── <歌名>.wav ×3
    ├── speed/                 # 任务1：变速版本
    │   ├── <歌名>_0.8x.mp3 ×3
    │   └── <歌名>_1.2x.mp3 ×3
    ├── original/              # 任务2：原始MP3（比特级复制）
    │   └── <歌名>.mp3 ×3
    ├── verse/                 # 任务2：主歌片段
    │   └── <歌名>_verse.mp3 ×3
    └── chorus/                # 任务2：副歌高光片段
        └── <歌名>_chorus.mp3 ×3
```

## 工作原理

1. **元数据提取**：从 ID3 标签读取标题、艺术家、歌词和封面（无需外部数据源）
2. **封面提取**：提取内嵌的 JPEG 封面并转换为 PNG
3. **音频转换**：转换为 48kHz 24bit WAV，使用 ffmpeg 的 atempo 滤镜创建 0.8x/1.2x 变速版本
4. **副歌/主歌检测**：使用四特征信号分析（RMS 能量、谱质心、人声频段占比、chroma 重复度），结合滑动窗口评分和位置先验
5. **歌词 DOCX**：生成格式化的 Word 文档，支持中文字体

## 算法

副歌检测采用多特征投票方法：
- **RMS 能量**：较响的片段通常为副歌
- **谱质心**：副歌通常更"明亮"
- **人声频段占比**：识别人声存在
- **Chroma 重复度**：副歌是最重复的片段（最强特征）

滑动窗口对这些特征的组合进行评分，并加入位置先验（副歌通常出现在歌曲的 50%-85% 区间）。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 2 | 用法/输入错误（目录不存在、未找到音频文件） |
| 3 | 未找到 ffmpeg |
| 4 | 部分文件处理失败 |

## 测试

```bash
# 单元测试（快速，无需 ffmpeg）
pytest tests/test_naming.py tests/test_lyrics.py tests/test_analysis.py

# 集成测试（需要 ffmpeg 和测试音频文件）
pytest tests/test_integration.py -m integration

# 全部测试
pytest tests/
```

## 项目结构

```
splitaudio/
├── pyproject.toml
├── README.md
├── docs/
│   ├── implementation-plan.md
│   └── completion-report.md
├── src/splitaudio/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # CLI 入口
│   ├── errors.py           # 异常层次定义
│   ├── ffmpeg_runner.py    # 工具解析 + subprocess 封装
│   ├── naming.py           # 文件名清理
│   ├── discovery.py        # 递归音频文件扫描器
│   ├── metadata.py         # 元数据提取（ffprobe/ffmetadata）
│   ├── analysis.py         # 核心副歌/主歌检测算法
│   ├── covers.py           # 封面提取
│   ├── audiotasks.py       # WAV/变速/裁剪处理
│   ├── lyrics_docx.py      # DOCX 歌词生成
│   └── tasks.py            # 任务编排
└── tests/
    ├── conftest.py
    ├── test_naming.py
    ├── test_lyrics.py
    ├── test_analysis.py
    └── test_integration.py
```

## 许可证

仅供内部使用。
