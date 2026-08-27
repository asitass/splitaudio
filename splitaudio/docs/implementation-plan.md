# splitaudio 实施方案（详细设计文档）

> **文档版本**：v1.0（2026-08-27）
> **任务来源**：`/home/ubuntu/test-project/test/README.txt` 招聘测试题（时间限制：两天）
> **文档性质**：完整实施方案。本文档基于**三轮实证验证**（元数据探查 → 算法在真实数据上运行调参 → ffmpeg 全链路管道验证）与**两轮上网技术调研**编写，所有关键参数与命令均已在真实输入数据上验证，非纸面设计。
> **状态**：方案已定稿，待按第 11 章路线图实施。

---

## 目录

1. [任务解读](#1-任务解读)
2. [输入数据分析（实证）](#2-输入数据分析实证)
3. [技术调研结论](#3-技术调研结论)
4. [总体设计](#4-总体设计)
5. [核心算法详细设计（副歌/主歌检测）](#5-核心算法详细设计副歌主歌检测)
6. [模块详细设计](#6-模块详细设计)
7. [ffmpeg 命令参考（已实证）](#7-ffmpeg-命令参考已实证)
8. [docx 歌词文档生成设计](#8-docx-歌词文档生成设计)
9. [跨平台与幂等设计](#9-跨平台与幂等设计)
10. [测试方案](#10-测试方案)
11. [实施路线图](#11-实施路线图)
12. [风险与回退](#12-风险与回退)
13. [附录 A：实证数据](#13-附录-a实证数据)
14. [附录 B：调研来源](#14-附录-b调研来源)
15. [附录 C：术语表](#15-附录-c术语表)

---

## 1. 任务解读

### 1.1 测试题原文要求

**测试题 1（普通难度）**——test 目录中有 3 个音频文件，根据 3 个音频文件**本身的信息**，交付以下内容在 `output` 文件夹里：

| 交付项 | 要求 |
|---|---|
| `cover/` | 封面图片，**PNG 格式** |
| `audio/` | 每首歌 3 个音频文件：① 一个 **wav 文件 48kHz 24bit**；② 一个 **0.8 倍速的 mp3**；③ 一个 **1.2 倍速的 mp3** |
| `lyrics/` | 歌词，**docx** 格式 |

- 通过条件：**随机运行两次**，在 Windows、macOS、Linux **任意两个机器**下运行成功
- 技术栈/大小/时长/是否安装均不受限，能运行即可，但需附上**运行注释或文档**

**测试题 2（挑战难度）**——提供三个音频文件的**副歌部分的高光裁剪**，交付：

| 交付项 | 要求 |
|---|---|
| `audio/` | 每首歌 3 个文件：① **原始音频 mp3**；② 一段**主歌**的 mp3；③ 一段**副歌**的 mp3 |
| `lyrics/` | 歌词 docx |

- 通过条件：会在 **Linux 系统**下运行

**通用要求**：
- 推荐运行方式（终端）：`splitaudio <文件夹路径>`，例：`splitaudio ~/user/documents/test`
- 可以提交半成品，但务必附上与 AI 的全部对话过程（能分辨用户提问与机器回答即可）
- ⚠️ **提醒**：请自行保留本次与 AI 的全部会话记录作为交付材料

### 1.2 需求拆解与关键决策

| 需求点 | 拆解结论 |
|---|---|
| "根据音频文件本身的信息" | 元数据（ID3 tags）、内嵌封面、内嵌歌词全部从文件自身提取，**不依赖任何外部数据源** |
| 封面 PNG | 3 个源文件均内嵌 360×360 mjpeg 封面（attached_pic 流），提取后转码 PNG |
| wav 48kHz 24bit | `pcm_s24le`（RIFF 小端规范）+ 48000Hz + 双声道重编码 |
| 0.8/1.2 倍速 | ffmpeg `atempo` 滤镜（保音高变速，0.8/1.2 均在单级合法区间内） |
| 歌词 docx | 从 ID3 `lyrics-eng` tag 提取（带段落结构标记），python-docx 排版生成 |
| 副歌高光裁剪 | **核心挑战**：源文件歌词无时间戳，需信号分析定位副歌/主歌时间区间（见第 5 章） |
| 跨平台运行两次 | Python 3 + ffmpeg 的组合在三平台均可安装；幂等设计（重复运行覆盖成功，见第 9 章） |
| `splitaudio <文件夹路径>` | Python 包 entry point（`pip install .` 后获得命令），亦支持 `python -m splitaudio` |

### 1.3 已确认的产品决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| 代码位置 | `/home/ubuntu/test-project/splitaudio/` | 与 `test/` 测试数据目录平级，交付结构清晰 |
| 技术栈 | Python 3.10+ / numpy / python-docx / 外部 ffmpeg | 环境已就绪；三平台可装；依赖最少 |
| 副歌检测方案 | 信号处理启发式（四特征投票），**不用** ASR/DL | 两天时限、跨平台免重型依赖、对标准结构 Suno 歌已实证有效 |
| 输出组织 | 两题合并一个 `output/` | 两题推荐命令相同，一次运行产出全部交付物 |
| 模拟数据 | **禁止**（项目规则） | 所有降级路径均输出真实音频裁剪，见 5.6 降级链 |

---

## 2. 输入数据分析（实证）

以下数据全部由 `ffprobe -show_streams -show_format -of json` 对真实文件探查所得（2026-08-27）。

### 2.1 文件清单

位置：`/home/ubuntu/test-project/test/source/`（注意：音频在 `test/` 的 **`source/` 子目录**，因此工具必须**递归扫描**输入文件夹）

| 文件 | 大小 | 时长 | 采样率 | 声道 | 码率 |
|---|---|---|---|---|---|
| Out of Nowhere.mp3 | 3,196,966 B | 141.624s | 48kHz | 立体声 | ~179kbps |
| 我想大概是你变了.mp3 | 3,381,625 B | 144.192s | 48kHz | 立体声 | ~186kbps |
| 青春是我们写不完的旧书.mp3 | 3,394,309 B | 144.984s | 48kHz | 立体声 | ~186kbps |

### 2.2 元数据（ID3 tags，三文件结构一致）

| tag | 值（示例） | 用途 |
|---|---|---|
| `title` | 歌名（如 `我想大概是你变了`） | 输出文件命名、docx 标题 |
| `artist` | `geojol` | docx 副标题 |
| `comment` | `made with suno; created=...` | 判定为 Suno 生成（结构先验依据） |
| `lyrics-eng` | **完整歌词**，`\n` 分行，带段落标记 | docx 歌词、结构先验（段落顺序） |
| encoder | `Lavf60.16.100` | — |

**歌词结构标记**（来自 `lyrics-eng`，用于结构先验）：

| 文件 | 段落顺序 |
|---|---|
| Out of Nowhere | `[Verse 1] [Verse 2] [Chorus] [Bridge] [Verse 1] [Verse 2] [Final Chorus]` |
| 我想大概是你变了 | `[verse] [Bridge] [chorus]` ×2 |
| 青春是我们写不完的旧书 | `[verse] [Bridge] [chorus]` ×2 |

### 2.3 内嵌封面

每个文件含 index=1 的 **mjpeg 视频流**（`disposition.attached_pic=1`，`TAG:title=Cover`），360×360，`yuvj420p`。→ 封面交付物直接从此流提取并转 PNG。

### 2.4 对实现的直接推论

1. **所有交付物原料都在文件内**：title/artist/歌词/封面 → 完全满足"根据音频文件本身的信息"
2. 音频在子目录 → `discovery` 必须递归
3. 三首均为 ~142-145s 标准结构流行歌 → 算法参数按此时长域调优（实证有效）
4. 中文歌名/歌词 → 文件名清理与 docx 中文字体是跨平台关键点（见 6.6、第 8 章）

---

## 3. 技术调研结论

> 两轮上网调研（subagent，DuckDuckGo 检索 + 文献/仓库抓取）+ 本机三轮实证。来源链接见附录 B。

### 3.1 副歌/高光检测：算法与开源库对比

| 方案 | 原理 | 结论 |
|---|---|---|
| **纯能量法（RMS argmax）** | 副歌最响 | **文献实证最弱基线**（ISMIR'13：仅响度特征 F≈0.48，随机基线 0.36）。本任务数据上亦有失败案例：英文歌 128-138s 器乐 outro 能量全曲最高（1.08-1.16）但**不是**副歌 → 必须与其他特征组合 |
| **重复段检测**（Bartsch & Wakefield 2001；Goto 2003） | 副歌是最重复的段（chroma 自相似矩阵） | **最强单一线索**，流行歌 ~80% 正确率。pychorus（213★, MIT）为参考实现 |
| 特征判别式（chorusness） | 副歌更响/更亮/动态更平 | ISMIR'13 结论支持"更亮"（谱质心）作为辅助特征 |
| 神经端到端（allin1 / SpecTNT） | DL 直接输出段落标签 | allin1 不支持 Python 3.12 且 Windows 无 NATTEN；all-in-one-infer 需 torch+demucs（分钟级/首）——**超出两天/跨平台约束，不采用** |
| MSAF | 结构分割+聚类 | 输出无语义标签（A/B/C 簇），需自写映射，性价比低，不采用 |
| Whisper ASR 歌词对齐 | 语音识别对齐时间戳 | 最准但需下载数 GB 模型、跨平台评审环境难保障，不采用（留作未来增强） |

**采纳**：自实现「能量 + 亮度 + 重复度（+人声占比辅助）」多特征投票 + 位置先验，numpy 手写（~150 行），零额外依赖。

**Suno 特性佐证**（调研）：Suno 输出偏安静、未极限压限（需后期母带）→ **段落间动态对比真实存在**，能量/亮度特征有效的前提成立。

### 3.2 工程实践要点（调研确认）

| 主题 | 结论 |
|---|---|
| ffmpeg 分发 | `imageio-ffmpeg`（wheel 内嵌 ffmpeg 二进制 ~20-30MB，**无 ffprobe**）可作兜底；解析链 `env var → PATH → imageio-ffmpeg → 报错`。ffprobe 缺失时用 `ffmpeg -f ffmetadata` + stderr `Duration:` 降级 |
| subprocess | 必加 `-nostdin`（防后台 stdin 挂起）；PCM 用 `subprocess.run(capture_output=True)`（~6MB 有界安全）；禁 `shell=True` |
| atempo | 0.8/1.2 落在所有历史版本单级合法区间（旧 [0.5,2.0] / 新 [0.5,100]），**保音高**；变速后 mp3 时长偏差 25-75ms（1152 样本/帧 + LAME 576 延迟）→ 断言用绝对容差 ±0.2s |
| wav 24bit | 必须 `pcm_s24le`（WAV/RIFF 小端规范；`s24be` 属 AIFF 系）；README 需注明"24bit 为处理容器位深，源为有损 mp3" |
| python-docx 中文 | 先 `font.name`（创建 rPr）再 `rFonts.set(qn("w:eastAsia"), "宋体")`，顺序反了抛 AttributeError；宋体在 macOS 由 Word 自动替换（PingFang SC），不乱码 |
| Windows 编码 | 入口 `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`（防重定向/管道下 GBK 崩溃）；所有 `open()` 显式 `encoding="utf-8"` |

### 3.3 算法实证（本机对 3 首真实歌曲完整运行）

**第一轮（初版三特征）**——副歌窗口检测稳定收敛（Top5 候选几乎重合）：

| 歌曲 | 检测副歌窗 | 检测主歌窗 |
|---|---|---|
| Out of Nowhere | [87.8s, 107.8s] | [9.3s, 29.3s] |
| 我想大概是你变了 | [110.9s, 130.9s] | [8.6s, 28.6s] |
| 青春是我们写不完的旧书 | [110.4s, 130.4s] | [9.9s, 29.9s] |

发现并修复一个关键缺陷：初版重复度用**余弦相似度**，chroma L2 归一后全曲饱和在 0.98-0.99（无区分度）。

**第二轮（修正版）**——重复度改为「±0.5s chroma 上下文拼接 + Pearson 去均值相关」，区分度恢复（p10-p90 = 0.65-0.89，std ≈ 0.08-0.09），副歌区间重复度显著偏高。

**多特征必要性直接验证**：Out of Nowhere 的 128-138s 能量全曲最高（1.08-1.16）但亮度骤降（1.6-1.8kHz，副歌区为 2.6-3.2kHz）且人声占比低 → 判定为器乐 outro；三特征打分正确选择 [87.8, 107.8]（真实 Final Chorus）。**纯能量法在该数据上必错，多特征方案实证胜出。**

**结构规律**（1s 粒度曲线，见附录 A）：三首歌均在 ~30-31s 出现首次能量跳升（0.5→0.9，第一遍 bridge/chorus 来临）；前奏 0-10s 低能量；歌 3 在 68-70s 有段落间隙（0.47→0.07→0.11）。

### 3.4 ffmpeg 链路实证（管道验证，未落盘）

| 验证项 | 结果 |
|---|---|
| wav 转换 | `pcm_s24le + 48000Hz + 2ch + bits_per_raw_sample=24` ✅ |
| atempo 0.8/1.2 | 可正常编码（管道流 ffprobe duration=N/A 属正常——管道无法回读 Xing 头；写文件后正常，集成测试按文件断言） ✅ |
| 封面提取 | `PNG image data, 360 x 360, 8-bit/color RGB` ✅ |
| ffmetadata 降级 | title/artist/lyrics-eng 全部可得；**注意**：ffmetadata 格式把换行转义为行尾 `\`，解析时需还原 ✅ |
| stderr 时长 | `Duration: 00:02:24.19` 可正则解析 ✅ |

---

## 4. 总体设计

### 4.1 架构与数据流

```
splitaudio <FOLDER>
 └─ cli.main()
     ├─ ffmpeg_runner.resolve_tools()          # env → PATH → imageio-ffmpeg；ffprobe 可缺失(降级)
     ├─ discovery.find_audio_files(FOLDER)     # 递归扫描音频扩展名 → list[Path]
     ├─ metadata.probe(path) → TrackMeta       # ffprobe(或 ffmetadata 降级)：时长/tags/歌词/封面流
     ├─ tasks.run_task1(tracks, output/)       # 题1：封面PNG + 48k24bit wav + 0.8x/1.2x mp3 + 歌词docx
     │    ├─ covers.extract_cover()
     │    ├─ audiotasks.make_wav() / make_speed()
     │    └─ lyrics_docx.write_lyrics_docx()
     └─ tasks.run_task2(tracks, output/)       # 题2：原始mp3 + 主歌/副歌裁剪 + 共用歌词docx
          ├─ analysis.detect_sections()        # ★ PCM→四特征包络→滑窗打分→Span 定位
          └─ audiotasks.extract_clip()         # -ss/-t 裁剪 + afade 防爆音
```

### 4.2 项目结构

```
/home/ubuntu/test-project/splitaudio/
├── pyproject.toml            # [project.scripts] splitaudio = "splitaudio.cli:main"
│                             # 依赖: numpy, python-docx; 可选组 [fallback]: imageio-ffmpeg
├── README.md                 # 三平台安装/运行文档（含 24bit 容器位深说明）
├── docs/
│   ├── implementation-plan.md   # 本文档
│   └── completion-report.md     # 完成报告（实施后补）
├── src/splitaudio/
│   ├── __init__.py           # __version__
│   ├── __main__.py           # python -m splitaudio 入口
│   ├── cli.py                # argparse + 日志 + UTF-8 reconfigure + 退出码
│   ├── errors.py             # 异常层次
│   ├── ffmpeg_runner.py      # 工具解析链 + subprocess 封装
│   ├── naming.py             # sanitize_filename 跨平台文件名清理
│   ├── discovery.py          # 递归扫描音频
│   ├── metadata.py           # TrackMeta + probe + ffmetadata 降级 + parse_sections
│   ├── analysis.py           # ★核心：四特征包络 + 主/副歌检测 + 降级链
│   ├── covers.py             # attached_pic → PNG
│   ├── audiotasks.py         # make_wav / make_speed / extract_clip
│   ├── lyrics_docx.py        # docx 生成
│   └── tasks.py              # task1/task2 编排 + 幂等输出
└── tests/
    ├── conftest.py           # SPLITAUDIO_TEST_SOURCE env（默认 ../test），缺失 skip 集成测试
    ├── test_naming.py
    ├── test_lyrics.py
    ├── test_analysis.py      # 合成信号，不依赖 ffmpeg
    └── test_integration.py   # 真实端到端 + 幂等（marker: integration）
```

### 4.3 输出目录布局（两题合并，生成在输入文件夹内）

```
test/output/
├── cover/                     # ── 测试题 1 ──
│   ├── Out of Nowhere.png
│   ├── 我想大概是你变了.png
│   └── 青春是我们写不完的旧书.png
├── lyrics/                    # ── 测试题 1 + 2 ──
│   └── <歌名>.docx ×3
└── audio/
    ├── wav/                   # ── 测试题 1 ──  48kHz 24bit
    │   └── <歌名>.wav ×3
    ├── speed/                 # ── 测试题 1 ──  变速
    │   ├── <歌名>_0.8x.mp3 ×3
    │   └── <歌名>_1.2x.mp3 ×3
    ├── original/              # ── 测试题 2 ──  原始音频（shutil.copy2 比特级复制）
    │   └── <歌名>.mp3 ×3
    ├── verse/                 # ── 测试题 2 ──  主歌片段
    │   └── <歌名>_verse.mp3 ×3
    └── chorus/                # ── 测试题 2 ──  副歌高光片段
        └── <歌名>_chorus.mp3 ×3
```

文件名一律 `sanitize_filename(title tag)`（title 缺失回退文件名去扩展名）；两平台运行产出**一致文件名**（确定性）。

---

## 5. 核心算法详细设计（副歌/主歌检测）

### 5.1 特征提取（一次解码，四条包络）

**解码**：
```
ffmpeg -nostdin -v error -i IN -vn -ac 1 -ar 22050 -f s16le pipe:1
→ np.frombuffer(int16).astype(float32)/32768.0
```
- 22050Hz 单声道：段落级分析足够（chroma 上限 11kHz 覆盖基频+泛音），145s 仅 ~6.4MB，`capture_output` 管道安全
- `-vn` 显式跳过 attached_pic 封面流

**STFT**：帧长 8820（400ms）、hop 2205（100ms，10fps）、Hann 窗 → 幅度谱 `spec[nf, 4411]`，频率轴 `freqs = rfftfreq(8820, 1/22050)`

**四条包络**（各 10fps，1s 矩形滑动平均平滑）：

| # | 特征 | 计算式 | 依据 |
|---|---|---|---|
| 1 | RMS 能量 `rms` | `sqrt(mean(frame²))`，除以 `p95` 归一 | 副歌统计上更响（辅助特征） |
| 2 | 谱质心亮度 `cent` | `Σ(spec·f)/Σspec`（Hz） | 副歌更亮（ISMIR'13）；**实证关键**：区分器乐 outro |
| 3 | 人声频段占比 `vocal` | `Σspec[200Hz–4kHz] / Σspec` | 主歌定位辅助（识别人声进入点） |
| 4 | 重复度 `rep` | 见 5.2 | **最强单一线索**（Bartsch/Goto） |

### 5.2 重复度计算（实证修正版）

```
1. chroma：对 >55Hz 的幅度谱按 pitch class 折叠为 12 维（midi = 69+12·log2(f/440)，pc = midi mod 12）
   → ch[nf, 12]（保留原始幅度，不做 L2 归一）
2. 上下文拼接：每帧取 ±0.5s（±5 帧）chroma 横拼 → ctxv[nf, 132]
3. Pearson 相关 SSM：m = ctxv - row_mean；mn = m/||m||；sim = mn @ mn.T   [nf×nf ≈ 1450²]
4. 排除邻域：sim[i, i±10s] = -2（段落不能和自己的邻域匹配）
5. rep[i] = sim[i].max()    （每帧与全曲最相似帧的相似度）
```

**实证依据**：初版用 L2 归一 chroma 的余弦相似度 → 全曲饱和 0.98-0.99 无区分度；改用「去均值 Pearson + 时间上下文」后 p10-p90 = 0.65-0.89（std 0.076-0.094），副歌区间显著偏高（如中文歌 110-130s 区间 rep 0.84-0.93 vs 前奏 0.37-0.77）。

### 5.3 副歌定位（滑窗打分 + 位置先验）

```
score(i) = mean(z(rms)[i:i+W]) + mean(z(cent)[i:i+W]) + mean(z(rep)[i:i+W]) + prior(center_i)
其中 W = 200 帧（20s），stride = 1 帧，z() 为全曲 z-score
prior：center 归一位置 pos = center_i/dur
       pos ∈ [0.50, 0.85] → +1.0      # 副歌先验区
       pos < 0.50          → +0.5      # 前半段（首遍副歌也可能在此）
       pos > 0.88          → +0.2      # 尾奏惩罚（防 outro argmax）
搜索域：pos ∈ [0.15, 0.90]
副歌窗 = argmax(score)
```

**边界精修**：
1. 窗口左/右端各在 ±4s 内向外找最近能量谷（`e[j] ≤ e[j±3帧]` 且 `e[j] < 0.75·窗内均值`）
2. 找到谷 → 边界对齐到谷（记 `aligned=True`）；未找到 → 保持窗口边界（`aligned=False`，该端用长淡变）
3. 长度 clamp 至 [15s, 25s]（超长向内收缩保持能量质心 `Σt·e/Σe` 居中）

**实证预期**（实施后应复现，容差 ±2s）：
- Out of Nowhere → [~88, ~108]（成功避开 128-138s 器乐 outro）
- 我想大概是你变了 → [~111, ~131]
- 青春是我们写不完的旧书 → [~110, ~130]

### 5.4 主歌定位（前奏后、首次副歌前）

```
1. chorus_level = mean(rms_n[副歌窗±20帧])
2. 首次副歌来临点 c1：在 [0.25·dur, chorus.start - 10s] 内找首个
   mean(rms_n[t : t+80帧]) > 0.85 · chorus_level 的 t      # 实证 ≈ 30-31s
3. intro_end = max(5s, 0.06·dur, 首个 rms_n > 0.45·p95 且持续 2s 的点)   # 实证 ≈ 5-10s
4. verse = [intro_end, min(intro_end + 20s, c1 - 1s)]
5. 时长下限 12s（不足则 start 前移至 c1 - 13s）；边界同样谷对齐
```

**实证预期**：三首歌主歌 ≈ [9, 29]（前奏之后、首次能量跳升之前的中低能量人声区）。

### 5.5 置信度

```
confidence = clamp( (mean(chorus_rms)/p50(rms) - 1) / 1.0, 0, 1 )   # 实测三首约 1.5-2.1 → 高置信
方向一致性检查：副歌窗内 rms/cent/rep 的 z 均值是否均 > 0（记录进日志）
```

`-v` 下打印：四条包络每 10s 概要、检测 Span、方法名、置信度（答辩可解释性）。

### 5.6 降级链（L0-L3，全部真实裁剪，无模拟数据）

| 级别 | 触发条件 | 行为 |
|---|---|---|
| **L0** `energy+brightness+repetition` | 正常路径 | 5.3/5.4 全流程 |
| **L1** `energy+brightness` | 重复度异常（SSM 含 NaN / rep 全曲 std < 0.02） | 去掉 rep 特重打分 |
| **L2** `prior-fallback` | 能量平坦（p95/p50 < 1.15）或解码帧数 < 30s | 直接用 Suno 结构先验：chorus = [0.72·dur-10s, 0.72·dur+10s]，verse = [0.06·dur, +20s]；两端长淡变；WARNING 日志 + confidence=0.3 |
| **L3** per-file error | PCM 解码失败 / duration ≤ 0 | 该文件 ERROR 跳过，其余继续；进程退出码 4 |

> L2 是"用真实结构先验选取真实时间区间再从真实音频裁剪"，**不是编造数据**（符合项目"禁止模拟数据"规则）；置信度与方法名写入日志，诚实可查。

### 5.7 裁剪与防爆音

- ffmpeg 输入寻址：`-ss <start> -t <dur>` 置于 `-i` 之前（mp3 帧对齐由 6.x 重解码保证，精度 ±1 帧 ≈ 26ms，远小于容差）
- 淡变双档（`afade`）：
  - 边界对齐到能量谷 → 淡入/淡出各 **50ms**（仅消咔哒声，音乐上无感）
  - 边界未对齐（降级）→ 淡入 **300ms**、淡出 **600ms**（听感可接受的补救）

---

## 6. 模块详细设计

> 签名以 Python 3.10+ 类型标注；所有模块日志走 `logging`（stderr），中文消息。

### 6.1 errors.py — 异常层次

```python
class SplitaudioError(Exception): ...        # 基类
class FFmpegNotFoundError(SplitaudioError): ...   # 附三平台安装指引
class NoAudioError(SplitaudioError): ...          # 输入目录无音频文件
class ProbeError(SplitaudioError): ...            # 元数据探测失败
```

### 6.2 ffmpeg_runner.py — 工具解析链与 subprocess

```python
@dataclass(frozen=True)
class Tools:
    ffmpeg: str          # 必须可用
    ffprobe: str | None  # 可缺失 → metadata 走降级路径

def resolve_tools() -> Tools:
    # ffmpeg: SPLITAUDIO_FFMPEG env → shutil.which("ffmpeg") → imageio_ffmpeg.get_ffmpeg_exe()
    #         （try import，[fallback] 可选依赖）→ 都失败抛 FFmpegNotFoundError（退出码 3）
    # ffprobe: SPLITAUDIO_FFPROBE env → shutil.which("ffprobe") → None

def run(cmd: list[str], *, timeout: int = 300) -> bytes:
    # subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    # 失败：CalledProcessError 转译，异常消息附 stderr 尾部 500 字节（可排查）
```

- 统一命令前缀：`-y -nostdin -hide_banner -loglevel error`
- 禁 `shell=True`（跨平台 + 注入安全）；参数一律 list 形式（路径含中文/空格天然安全）

### 6.3 naming.py — 跨平台文件名清理

```python
def sanitize_filename(name: str, *, max_len: int = 120) -> str
```

规则（三平台统一执行，保证跨平台产出一致）：
1. 替换 `<>:"/\|?*` 与控制字符（`ord < 0x20`）为 `_`
2. Windows 保留名（`CON PRN AUX NUL COM1-9 LPT1-9`，不区分大小写）→ 追加 `_file`
3. 去除尾部点与空格（Windows 禁止）
4. 截断至 120 字符；空结果回退 `untitled`
5. **中文字符原样保留**（实证：歌名即中文，三平台 NTFS/APFS/ext4 均安全）

### 6.4 discovery.py — 递归扫描

```python
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}
def find_audio_files(root: Path) -> list[Path]
    # root.rglob("*") 按扩展名过滤 + 排序（确定性）；不存在/非目录 → NoAudioError 路径（退出码 2）
```

### 6.5 metadata.py — 元数据与歌词

```python
@dataclass
class LyricSection:
    marker: str          # 原文标记，如 "[chorus]"；无标记段为 ""
    lines: list[str]

@dataclass
class TrackMeta:
    path: Path
    title: str           # title tag → 回退文件名去扩展名
    artist: str
    duration: float
    lyrics: str
    sections: list[LyricSection]
    has_cover: bool      # 存在 attached_pic/视频流

def probe(path: Path, tools: Tools) -> TrackMeta
def _pick_lyrics(tags: Mapping[str, str]) -> str
    # key 归一化（lower + '-'/'_' 等价）匹配 lyrics-eng / lyrics / unsynclyrics
def parse_sections(lyrics: str) -> list[LyricSection]
    # 正则 ^\[(.+?)\]\s*$ （MULTILINE | IGNORECASE）切分；无任何标记 → 整篇一个 section
```

**主路径**（有 ffprobe）：一次 `ffprobe -v error -show_streams -show_format -of json` 取全部。
**降级路径**（无 ffprobe，imageio-ffmpeg 场景）：
- `ffmpeg -nostdin -i IN -f ffmetadata pipe:1` → 解析 `key=value` tags。**关键细节**：ffmetadata 把歌词内换行转义为行尾 `\`，解析时需将 `\` 行接还原为换行（含 `\\`→`\`、`\;` 等转义处理，实证确认必要）
- 时长：stderr `Duration: HH:MM:SS.ms` 正则解析（实证：`00:02:24.19` → 144.19s）
- 封面存在性：`-f ffmetadata` 不可靠 → 用 `ffmpeg -i IN -map 0:v -frames:v 1 -f null -` 的退出码探测

### 6.6 analysis.py — 核心算法（见第 5 章）

```python
@dataclass
class Span:
    start: float; end: float
    @property def dur(self) -> float

@dataclass
class Sections:
    verse: Span
    chorus: Span
    confidence: float      # 0~1
    method: str            # "features" | "energy+brightness" | "prior-fallback"

def decode_envelope(path: Path, tools: Tools, *, sr: int = 22050, hop_ms: int = 100) -> Envelope
    # Envelope: rms_n / cent_s / voc_s / rep 四条 np.ndarray（等长 10fps）+ duration
def detect_sections(env: Envelope) -> Sections
    # 纯函数：只依赖包络数组 → 单元测试用合成信号直接测（不需要 ffmpeg）
```

### 6.7 covers.py / audiotasks.py / lyrics_docx.py / tasks.py

```python
# covers.py
def extract_cover(src: Path, dst: Path, tools: Tools) -> bool
    # ffmpeg -map 0:v:0 -frames:v 1 -update 1 OUT.png；无视频流返回 False（warning 跳过，不伪造占位图）

# audiotasks.py
def make_wav(src, dst, tools) -> None            # 48kHz/24bit/2ch，见第 7 章
def make_speed(src, dst, tempo: float, tools)    # tempo ∈ {0.8, 1.2}
def extract_clip(src, dst, span: Span, *, fade_in: float, fade_out: float, tools) -> None

# lyrics_docx.py
def write_lyrics_docx(meta: TrackMeta, dst: Path) -> None     # 见第 8 章

# tasks.py
def run_task1(tracks, out_dir, tools, log) -> list[Path]      # 封面/wav/speed/docx
def run_task2(tracks, out_dir, tools, log) -> list[Path]      # original/verse/chorus
    # original 用 shutil.copy2（比特级一致）；单文件失败 ERROR 继续下一首
```

### 6.8 cli.py — 入口与退出码

```
usage: splitaudio [-h] [--task {1,2,all}] [--output DIR] [-v] [--version] FOLDER

FOLDER     输入文件夹（递归扫描音频）
--task     默认 all（一次产出两题全部交付物）
--output   默认 FOLDER/output
-v         DEBUG 日志（打印每条 ffmpeg 命令、包络概要、Span/置信度/方法）
```

- 入口第一行：`sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`
- 退出码契约：`0` 全部成功 ｜ `2` 用法/输入错误（目录不存在、无音频）｜ `3` ffmpeg 缺失 ｜ `4` 部分文件失败
- 日志 → stderr（`%(levelname)-7s %(message)s`，默认 INFO）；stdout 保持干净（便于脚本化管道）

---

## 7. ffmpeg 命令参考（已实证）

> 全部命令实际前缀：`-y -nostdin -hide_banner -loglevel error`（下表省略）。

| 用途 | 命令 | 断言（集成测试） |
|---|---|---|
| wav 48k 24bit | `ffmpeg -i IN -map 0:a:0 -ar 48000 -ac 2 -c:a pcm_s24le OUT.wav` | ffprobe: `codec_name=pcm_s24le, sample_rate=48000, channels=2, bits_per_raw_sample=24`（已实证 ✅） |
| 变速 mp3 | `ffmpeg -i IN -map_metadata 0 -filter:a "atempo=0.8" -c:a libmp3lame -b:a 192k -id3v2_version 3 OUT.mp3` | 时长 ≈ 原时长/0.8，**绝对容差 ±0.2s**（偏差源：1152 样本/帧 + LAME 576 延迟，实证量级 25-75ms） |
| 封面 PNG | `ffmpeg -i IN -map 0:v:0 -frames:v 1 -update 1 OUT.png` | `file`/PIL: `PNG 360×360 RGB`（已实证 ✅） |
| 片段裁剪 | `ffmpeg -ss <start> -t <dur> -i IN -map 0:a:0 -af "afade=t=in:st=0:d=<FI>,afade=t=out:st=<dur-FO>:d=<FO>" -c:a libmp3lame -b:a 192k -id3v2_version 3 OUT.mp3` | 时长 ∈ [12s, 30s]；chorus 片段平均 RMS > 全曲 p50 |
| PCM 分析解码 | `ffmpeg -i IN -vn -ac 1 -ar 22050 -f s16le pipe:1` | int16 字节流 → numpy（实证 ✅） |
| 元数据降级 | `ffmpeg -i IN -f ffmetadata pipe:1` | tags 含 title/artist/lyrics-eng；行尾 `\` 还原换行（实证 ✅） |
| 时长降级 | `ffmpeg -i IN -f null -`（读 stderr） | `Duration: 00:02:24.19` 正则（实证 ✅） |

说明：
- `-id3v2_version 3`：ID3v2.3 是 Windows 资源管理器/旧播放器兼容性最好的版本
- `original/` 交付用 `shutil.copy2` 纯复制（不经重编码，保留原始比特与全部元数据）
- 变速保持音高（atempo 为 WSOLA 类 time-stretch），题目"倍速"语义即此

---

## 8. docx 歌词文档生成设计

### 8.1 中文字体（跨平台不乱码的关键）

```python
from docx import Document
from docx.oxml.ns import qn

doc = Document()
style = doc.styles["Normal"]
style.font.name = "Times New Roman"                        # ① 先设西文字体（同时创建 rPr 节点）
style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")     # ② 再设东亚字体（顺序不可反，否则 AttributeError）
# 每个含中文的 run 上冗余设置一次（防样式继承失效）：
#   run.font.name = "Times New Roman"
#   run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
```

- 原理：`font.name` 只写 `w:ascii/w:hAnsi`（西文），中文渲染看 `w:eastAsia`，不设则回落主题默认导致字体不生效
- 宋体在 macOS/Linux 缺失时由 Word 自动替换（PingFang SC / 思源黑体系），**文档正常打开不乱码**（调研确认）

### 8.2 排版结构

```
[标题]      title tag            22pt 加粗 居中
[副题]      artist · 时长(mm:ss)  11pt 灰色 居中
[空行]
[段落标记]   [chorus] · 副歌       加粗 深灰 段前12pt 段后6pt
[歌词行]                          Normal 12pt 1.5倍行距
...（逐段落重复）
```

段落标记中文对照映射：

| 原标记（匹配小写子串） | 显示 |
|---|---|
| `verse` | `[verse] · 主歌` |
| `chorus` | `[chorus] · 副歌` |
| `bridge` | `[bridge] · 桥段` |
| `intro` / `outro` | `[intro] · 前奏` / `[outro] · 尾奏` |
| 其他 | 原样显示 |

- 歌词为空：仍生成 docx，正文注明"（未找到内嵌歌词）"（诚实交付，占位可查）
- 验证：集成测试用 python-docx 读回，断言含 title、至少一个段落标记、至少一行歌词原文

---

## 9. 跨平台与幂等设计

### 9.1 通过条件逐项覆盖

| 题目要求 | 设计响应 |
|---|---|
| Windows/macOS/Linux 任意两平台 | Python 3.10+ + ffmpeg：三平台均有成熟安装渠道（README 分别给出 winget/brew/apt 指引）；无 C 扩展依赖（numpy/python-docx 均有三平台 wheel） |
| 随机运行两次 | **幂等**：输出目录 `mkdir(exist_ok=True)` + ffmpeg 全 `-y` + docx/png 覆盖写 + **确定性文件名**（无时间戳/随机后缀）→ 第二次运行结果与第一次一致且退出码 0（集成测试断言） |
| 附运行注释/文档 | README.md：三平台安装+运行+参数+故障排查；docx 内含来源说明行 |
| Linux 下运行（题2） | 开发即 Linux（WSL2）；CI 式集成测试在本机真实跑通 |

### 9.2 编码与路径

- 入口 `reconfigure(encoding="utf-8", errors="replace")`：防 Windows 下 stdout 重定向/管道时 GBK 编码中文/特殊字符崩溃（`chcp 65001` 对非 tty 无效，调研实证）
- 所有 `open()` 显式 `encoding="utf-8"`（Python 3.15 才默认 UTF-8 模式）
- 全程 `pathlib.Path`；subprocess 参数 list（路径含中文/空格安全，无 shell 引号问题）

### 9.3 ffmpeg 可用性（评审机保险）

```
SPLITAUDIO_FFMPEG / SPLITAUDIO_FFPROBE 环境变量
  → shutil.which()（PATH）
  → imageio_ffmpeg.get_ffmpeg_exe()（pip install ".[fallback]" 时可用；wheel 内嵌 ffmpeg，无 ffprobe → 走 6.5 降级路径）
  → 全部失败：FFmpegNotFoundError + 三平台安装命令 + 官网链接，退出码 3
```

### 9.4 代码级跨平台自查清单（实施后 review 项）

- [ ] 无 `shell=True`
- [ ] 无字符串拼接命令（全部 list）
- [ ] 全部 `pathlib`，无手写 `/` 拼接
- [ ] 入口 reconfigure UTF-8
- [ ] 所有 `open()` 带 `encoding="utf-8"`
- [ ] 文件名全部过 `sanitize_filename`
- [ ] 无平台分支代码（同一代码路径三平台运行）
- [ ] 输出文件名确定性（无时间戳/随机）

---

## 10. 测试方案

### 10.1 单元测试（不依赖 ffmpeg，毫秒级，CI 可跑）

| 文件 | 用例 |
|---|---|
| `test_naming.py` | 非法字符替换；`CON`/`com1` 保留名处理；尾部点/空格；`我想大概是你变了` 原样保留；120 字符截断 |
| `test_lyrics.py` | `parse_sections`：混合大小写标记、`[Verse 1]` 带编号、无标记整篇、空串；`_pick_lyrics`：`LYRICS-ENG`/`lyrics_eng`/`unsynclyrics` 归一匹配 |
| `test_analysis.py` | **合成包络**（np.concatenate 构造，不用 ffmpeg）：① 低30s+高20s+谷+高25s → chorus 命中末段高区、verse 在首升点前；② 全平包络 → `method="prior-fallback"` 且 Span 在先验位置；③ <30s 包络 → 保护分支不越界；④ 40s 连续高能 → clamp ≤ 25s |

### 10.2 集成测试（`-m integration`，真实数据端到端）

`conftest.py`：`SPLITAUDIO_TEST_SOURCE`（默认 `../test`）指向测试目录，缺失自动 skip。

通过 `subprocess.run([sys.executable, "-m", "splitaudio", test_dir])` 走**真实 CLI 入口**：

1. **目录树**：`output/{cover,lyrics,audio/{wav,speed,original,verse,chorus}}` 齐全，3 首歌 × 7 文件全存在
2. **wav 规格**：ffprobe 断言 `pcm_s24le + 48000 + 2ch + 24bit`
3. **变速时长**：0.8x ≈ 原时长/0.8、1.2x ≈ 原时长/1.2，绝对容差 ±0.2s
4. **片段语义**：verse/chorus 时长 ∈ [12s, 30s]；**chorus 片段平均 RMS > 全曲 p50**（高光语义自检——副歌片段确实比全曲中位数响）
5. **PNG**：PIL 打开且 `format == "PNG"`
6. **docx**：python-docx 读回，含 title、段落标记、歌词原文
7. **幂等**：连续跑两次，第二次退出码 0 且全部断言复验通过（题目"随机运行两次"的硬性验证）
8. **退出码契约**：空文件夹 → 2；PATH 注入空 → 3
9. **算法回归**：三首歌检测 Span 与附录 A 实证结果偏差 ≤ ±2s（防调参回退）

### 10.3 手工验证（交付前）

- `-v` 运行查看包络概要与 Span 输出
- Windows/macOS 真机（或 VM）各跑一次 `splitaudio <test目录>`（题目要求两平台；本机 Linux 已由集成测试覆盖）

---

## 11. 实施路线图

> 总预算 ~14h（两天时限内富余）。S4 为题 1 保底里程碑。

| # | 内容 | 里程碑/验证 | 预计 |
|---|---|---|---|
| S1 | pyproject + 包骨架 + cli + errors + ffmpeg_runner + naming | `splitaudio --help` 可跑 | 0.5h |
| S2 | discovery + metadata（含 ffmetadata 降级） | 3 个真实文件打印 TrackMeta 与歌词段落 | 1.5h |
| S3 | covers + audiotasks(wav/speed) + lyrics_docx | 题 1 零件齐 | 2h |
| S4 | tasks.run_task1 编排，真实跑 test/ | **题 1 交付物完成（保底）**，ffprobe 抽查规格 | 1h |
| S5 | analysis 四特征 + 检测（移植实证代码） | 3 首歌 Span 与附录 A 一致（±2s） | 3h |
| S6 | extract_clip + run_task2 | 题 2 交付物完成 | 1.5h |
| S7 | 单元测试三件套 | pytest 绿 | 1.5h |
| S8 | 集成 + 幂等测试 | integration 绿 | 1.5h |
| S9 | README + docs/completion-report.md | 交付文档齐 | 1h |

策略：S4 完成即锁定题 1（普通难度）；S5-S6 攻题 2，L2 先验降级保证题 2 任何情况下有真实产出。

---

## 12. 风险与回退

| # | 风险 | 概率 | 缓解 |
|---|---|---|---|
| R1 | 评审机无 ffmpeg 或不在 PATH | 中 | 解析链 + imageio-ffmpeg 兜底（README 注明 `pip install ".[fallback]"`）+ 明确报错指引（退出码 3） |
| R2 | 副歌定位在陌生歌曲上偏差 | 中 | 三特征+先验已实证；L2 降级保底有真实产出；`-v` 输出检测细节可答辩 |
| R3 | Windows GBK 控制台/文件系统 | 中 | reconfigure+errors=replace；sanitize 统一规则；中文文件名已实证无害 |
| R4 | docx 中文显示异常 | 低 | 样式级+run 级双重 eastAsia 声明；宋体替换表成熟 |
| R5 | atempo 后 mp3 时长断言失败 | 低 | ±0.2s 绝对容差（实证偏差 25-75ms 量级，富余 3 倍） |
| R6 | ffprobe 缺失（imageio-ffmpeg 场景） | 中 | ffmetadata + stderr Duration 降级路径（已实证） |
| R7 | 两次运行结果不一致 | 低 | 确定性设计（无时间戳/随机）；幂等入集成测试硬断言 |
| R8 | 两天时间盒超限 | 低 | S1-S9 依赖排序，S4 保底；L2 降级代码量小 |

---

## 13. 附录 A：实证数据

### A.1 四特征曲线（1s 粒度，每 10s 摘录；2026-08-27 实测）

**Out of Nowhere（141.6s）**

| t(s) | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 | 140 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 能量 | 0.15 | 0.71 | 0.67 | 0.60 | 0.97 | 0.60 | 0.82 | 0.83 | 0.70 | 0.84 | 0.89 | 0.77 | 1.08 | 0.26 | 0.61 |
| 亮度kHz | 0.61 | 2.12 | 2.85 | 2.48 | 2.27 | 2.95 | 2.30 | 2.84 | 2.61 | 3.10 | 2.96 | 2.56 | 1.78 | 1.61 | 0.15 |
| 人声占比 | 0.25 | 0.60 | 0.55 | 0.51 | 0.51 | 0.67 | 0.43 | 0.63 | 0.53 | 0.61 | 0.46 | 0.42 | 0.37 | 0.50 | 0.18 |
| 重复度 | 0.38 | 0.65 | 0.78 | 0.86 | 0.81 | 0.84 | 0.81 | 0.73 | 0.78 | 0.82 | 0.74 | 0.83 | 0.78 | 0.73 | 0.55 |

> 解读：120-138s 能量全曲最高（1.08-1.16）但亮度骤降（1.6-1.8kHz）、人声占比低 → **器乐 outro**。三特征打分正确选择 [87.8, 107.8]（Final Chorus）。

**我想大概是你变了（144.2s）**

| t(s) | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 | 140 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 能量 | 0.07 | 0.51 | 0.66 | 0.94 | 0.85 | 0.99 | 1.14 | 0.93 | 0.79 | 0.87 | 0.66 | 0.96 | 1.10 | 0.83 | 0.25 |
| 亮度kHz | 1.78 | 2.80 | 3.57 | 3.15 | 3.37 | 3.29 | 3.02 | 3.57 | 2.94 | 3.76 | 2.66 | 2.93 | 4.36 | 3.79 | 2.36 |
| 人声占比 | 0.22 | 0.58 | 0.52 | 0.51 | 0.48 | 0.47 | 0.49 | 0.42 | 0.65 | 0.55 | 0.44 | 0.46 | 0.50 | 0.45 | 0.41 |
| 重复度 | 0.37 | 0.76 | 0.80 | 0.82 | 0.71 | 0.85 | 0.87 | 0.74 | 0.81 | 0.76 | 0.73 | 0.84 | 0.88 | 0.87 | 0.72 |

> 30s 处能量跳升（0.66→0.94）＝第一遍 bridge/chorus 来临；110-130s 高能+高亮+高重复 → 副歌高光区。

**青春是我们写不完的旧书（145.0s）**

| t(s) | 0 | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 | 110 | 120 | 130 | 140 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 能量 | 0.00 | 0.49 | 0.55 | 0.81 | 0.89 | 0.82 | 1.01 | 0.07 | 0.74 | 0.71 | 0.84 | 1.01 | 0.94 | 0.99 | 0.02 |
| 亮度kHz | 2.33 | 1.56 | 3.78 | 2.85 | 2.91 | 2.98 | 2.44 | 1.78 | 3.64 | 2.39 | 2.62 | 2.80 | 2.97 | 3.11 | 1.76 |
| 人声占比 | 0.22 | 0.94 | 0.51 | 0.54 | 0.52 | 0.58 | 0.57 | 0.86 | 0.59 | 0.58 | 0.59 | 0.59 | 0.57 | 0.61 | 0.83 |
| 重复度 | 0.42 | 0.54 | 0.73 | 0.85 | 0.79 | 0.78 | 0.82 | 0.74 | 0.71 | 0.66 | 0.84 | 0.83 | 0.89 | 0.83 | 0.66 |

> 10-16s 人声占比 0.87-0.96（清唱/简单伴奏的主歌开头）；68-70s 能量骤降（段落间隙）。

### A.2 算法检测结果（第二轮修正版，20s 滑窗）

| 歌曲 | 副歌窗 | 主歌窗 | 首次副歌来临 |
|---|---|---|---|
| Out of Nowhere | [87.8, 107.8] | [9.3, 29.3] | ~35.4s |
| 我想大概是你变了 | [110.9, 130.9] | [8.6, 28.6] | ~36.0s |
| 青春是我们写不完的旧书 | [110.4, 130.4] | [9.9, 29.9] | ~36.2s |

（此为实施 S5 的回归基准，容差 ±2s。）

### A.3 重复度特征修正前后对比

| 版本 | 方法 | 全曲分布 | 结论 |
|---|---|---|---|
| 初版 | L2 归一 chroma 余弦相似 | 0.97-0.99（饱和） | 无区分度，弃用 |
| 修正版 | ±0.5s 上下文拼接 + Pearson 去均值 | p10=0.66, p50=0.78, p90=0.87, std=0.08 | 有效，采用 |

---

## 14. 附录 B：调研来源

### 算法文献与开源库

- Bartsch & Wakefield, *To Catch a Chorus: Using Chroma-Based Representations for Audio Thumbnailing* — https://www.ee.columbia.edu/~dpwe/papers/BartW01-chorus.pdf
- Goto 2003, *A Chorus-Section Detecting Method for Musical Audio Signals* — https://www.researchgate.net/publication/4068562
- ISMIR 2013, *An analysis of chorus features in popular song* — https://webspace.science.uu.nl/~veltk101/publications/art/ismir2013-chorus.pdf
- Huang 2018, *Pop Music Highlighter*（能量法为最弱基线的实证） — https://arxiv.org/abs/1802.10495
- SpecTNT (ICASSP 2022) — https://arxiv.org/abs/2205.14700
- pychorus（重复检测参考实现, MIT） — https://github.com/vivjay30/pychorus
- MSAF — https://github.com/urinieto/msaf
- allin1 / all-in-one-infer（未采用的 DL 方案） — https://github.com/mir-aidj/all-in-one 、https://github.com/openmirlab/all-in-one-infer
- librosa（1.0.0 支持 py3.12） — https://pypi.org/project/librosa/
- Suno 结构标签指南 — https://tinystudio.fm/guides/song-structure-tags/
- Suno 响度/母带分析 — https://sunomaster.com/blog/suno-song-quiet-lufs-loudness

### 工程实践

- imageio-ffmpeg（ffmpeg 二进制兜底） — https://pypi.org/project/imageio-ffmpeg/ 、https://github.com/imageio/imageio-ffmpeg
- static-ffmpeg（评估后未采用：首用时联网下载） — https://pypi.org/project/static-ffmpeg/
- subprocess 管道死锁与 communicate — https://docs.python.org/3/library/subprocess.html
- ffmpeg `-nostdin` 必要性 — https://trac.ffmpeg.org/ticket/42
- atempo 参数范围（源码 `af_atempo.c`: 0.5-100） — https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavfilter/af_atempo.c
- LAME/mp3 帧延迟综述 — https://www.compuphase.com/mp3/mp3loops.htm
- ffmpeg 音频类型（le/be 字节序） — https://trac.ffmpeg.org/wiki/audio+types
- python-docx 中文字体 — https://www.biaodianfu.com/python-docx/ 、https://www.cnblogs.com/mhkj/articles/15869936.html
- Windows UTF-8 模式（PEP 686 / PYTHONUTF8） — https://peps.python.org/pep-0686/ 、https://docs.python.org/3/using/windows.html

---

## 15. 附录 C：术语表

| 术语 | 含义 |
|---|---|
| attached_pic | mp3 内嵌封面（以视频流形式挂在音频容器里） |
| atempo | ffmpeg 变速滤镜（保音高，WSOLA 类时域拉伸） |
| chroma | 色度特征：把频谱能量折叠到 12 个音高类（pitch class） |
| SSM | 自相似矩阵（Self-Similarity Matrix），帧与帧的特征相似度矩阵 |
| Pearson 相关 | 去均值的相关系数（相比余弦相似度可消除共模偏置） |
| 谱质心 | 频谱能量的加权平均频率，感知上对应"亮度" |
| RMS | 均方根（此处：逐帧音频能量） |
| z-score | 特征标准化：(x-均值)/标准差，使不同量纲特征可相加 |
| prior / 先验 | 基于歌曲结构规律的预期（如副歌多位于 0.5-0.85 归一位置） |
| outro / intro | 尾奏 / 前奏 |
| 幂等 | 同一输入重复运行得到相同结果且不报错 |
| entry point | pip 安装后生成的命令行入口（`splitaudio`） |
| Suno | AI 音乐生成服务；本测试 3 个输入文件均由其生成 |
| L0-L3 | 本方案的算法降级链级别（见 5.6） |

---

*本文档由三轮实证验证与两轮技术调研支撑编写。实施过程中如实际情况与预期偏差，将同步更新本文档并在 completion-report.md 中记录。*
