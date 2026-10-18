# mediashrink

一个命令行工具，用来转码和压缩**视频、音频、图片和 PDF** 文件。

```bash
mediashrink auto clip.mov photo.heic song.wav report.pdf
```

每个文件处理完会打印一行，包括输出文件名、压缩前后的大小和压缩比例，例如 `✓ photo.heic → photo.min.jpg  2.4 MB → 610.2 KB (25%)`（数字仅为示意）。

## 安装

需要 Python ≥ 3.12 和 [uv](https://docs.astral.sh/uv/)。处理视频和音频还需要把 [ffmpeg](https://ffmpeg.org/) 加入 PATH：

| 系统 | 安装 ffmpeg |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg` |

ffmpeg 需要带有对应的编码器：h265 用 `libx265`，h264 用 `libx264`，av1 用 `libsvtav1`，vp9 用 `libvpx-vp9`，webm 的音频用 `libopus`。上面这几种方式装的 ffmpeg 一般都带齐了；较老的发行版（如 Ubuntu 22.04 自带的 ffmpeg 4.4）可能缺 `libsvtav1`。可以用 `ffmpeg -encoders` 检查。

```bash
uv sync                  # 安装依赖
uv run mediashrink --help
uv tool install .        # 可选：全局安装，之后直接用 mediashrink 命令
```

下文的示例都假设已经全局安装。如果没有，在命令前加上 `uv run`。

## 快速上手

```bash
mediashrink auto *.mov *.jpg *.pdf                        # 按扩展名自动选择处理方式，使用默认参数
mediashrink video in.mov -c h265 --crf 28 --max-height 1080
mediashrink video in.mp4 -c av1 -f mkv -o out/            # out/ 不存在时会自动创建
mediashrink audio song.wav -f mp3 -b 192k
mediashrink image *.png -f webp -q 75 --max-size 1920 -o out/
mediashrink pdf scan.pdf -q 60 --max-image-size 1600
mediashrink info in.mp4                                   # 用 ffprobe 查看媒体信息（JSON 格式）
```

每个子命令都可以用 `--help` 查看完整选项。

## 输出规则

- **输出位置**：默认写到输入文件旁边，文件名为 `<原名>.min.<扩展名>`，例如 `photo.jpg` → `photo.min.jpg`。
- **`-o/--output`**：
  - 指向一个已存在的目录，或者一个不存在、且没有扩展名的路径（如 `out/`）时，按目录处理，不存在会自动创建，输出为 `<目录>/<原名>.<扩展名>`。
  - 否则按输出文件处理（只能用于单个输入）。
  - 目录名本身带点（如 `v1.0/`）时，需要先手动创建，否则会被当成文件名。
- **不覆盖**：已存在的输出文件不会被覆盖，除非加 `-y/--overwrite`。输入文件在任何情况下都不会被覆盖。
- **结果变大就丢弃**：输出不比输入小时，默认丢弃并给出提示。加 `--keep-larger` 可以保留，比如只是想转换格式时。
- **不留残缺文件**：处理过程中先写到隐藏的临时文件（`.part-<文件名>`），成功后才改成最终文件名。出错或按 Ctrl+C 中断时，临时文件会被删掉。
- **批量处理**：可以一次传多个文件。单个文件失败不影响其他文件。两个输入会写到同一个输出时（例如 `a.png` 和 `a.jpg` 都会变成 `a.min.jpg`），第二个会报错，不会覆盖第一个。
- **退出码**：全部成功（包括"变大被丢弃"）时为 0。有任何文件失败时为 1。参数错误时为 2。

## 元数据与隐私

默认会去掉可能泄露隐私的元数据，加 `--keep-metadata` 可以保留：

| 类型 | 默认去掉 | 始终保留 |
|---|---|---|
| 图片 | EXIF（GPS 位置、相机型号、拍摄时间等） | ICC 色彩配置（否则会偏色）；EXIF 中的旋转方向会先应用到像素上 |
| 视频、音频 | 容器级标签（GPS 位置、设备信息、创建时间、标题，音频的歌手/专辑等标签） | 每条流自己的标签，例如音轨语言 |

注意：音频默认也会去掉歌手、专辑等标签。整理音乐库时，记得加 `--keep-metadata`。

## 各子命令

### `video`

| 选项 | 默认值 | 说明 |
|---|---|---|
| `-c/--codec` | `h265` | `h264` / `h265` / `av1` / `vp9` |
| `-f/--format` | `mp4`（vp9 为 `webm`） | 容器格式：`mp4` / `mkv` / `webm` / `mov` |
| `--crf` | 按编码器：h264 `23`、h265 `28`、av1 `35`、vp9 `33` | 质量，数值越小画质越好、文件越大 |
| `--preset` | `medium` | `ultrafast` … `veryslow`；对 av1、vp9 也生效，会换算成它们各自的速度参数 |
| `--max-height` | 不缩放 | 只缩小不放大，例如 `1080` |
| `--fps` | 保持原帧率 | 输出帧率 |
| `--audio-bitrate` | `128k` | 音频码率；mp4/mkv/mov 用 AAC 编码，webm 用 Opus 编码 |
| `--no-audio` | | 去掉音轨 |

编码器和容器必须匹配，否则会在开始编码前直接报错：

| | h264 | h265 | av1 | vp9 |
|---|---|---|---|---|
| mp4 | ✓ | ✓ | ✓ | ✓ |
| mkv | ✓ | ✓ | ✓ | ✓ |
| mov | ✓ | ✓ | | |
| webm | | | ✓ | ✓ |

h265 输出为 mp4/mov 时会打上 `hvc1` 标签，方便 QuickTime 和苹果设备播放。mp4/mov 输出还会开启 `faststart`，便于网页边下边播。

### `audio`

| 选项 | 默认值 | 说明 |
|---|---|---|
| `-f/--format` | `m4a` | `mp3` / `m4a` / `aac` / `opus` / `ogg` / `flac`（flac 是无损格式，忽略码率） |
| `-b/--bitrate` | `128k` | 码率 |
| `--sample-rate` | 保持原采样率 | 例如 `44100`、`22050` |
| `--mono` | | 混成单声道 |

### `image`

| 选项 | 默认值 | 说明 |
|---|---|---|
| `-f/--format` | 保持原格式；GIF → `webp`；其他格式 → `jpg` | `jpg` / `png` / `webp` / `avif` |
| `-q/--quality` | `80` | 1–100；PNG 是无损格式，只做无损优化，忽略此项 |
| `--max-size` | 不缩放 | 最长边的像素数，例如 `1920` |

- **输入格式**：上面四种之外，还能读 BMP、TIFF、GIF，以及 HEIC/HEIF（例如 iPhone 照片）。
- **动图**：动态 GIF、APNG、WebP、AVIF 转成 webp、png 或 avif 时，保留所有帧和每帧时长。动图如果指定输出 jpg 会报错，因为 JPEG 只能保留第一帧。

### `pdf`

| 选项 | 默认值 | 说明 |
|---|---|---|
| `-q/--image-quality` | `70` | 内嵌图片重新编码为 JPEG 时的质量 |
| `--max-image-size` | `2000` | 内嵌图片最长边的像素数 |

处理方式：把内嵌的 RGB、灰度、调色板图片重新编码为 JPEG（压不小的保持原样），再重新压缩所有数据流，并删掉没有被引用的资源。

### `auto`

按扩展名选择处理方式，全部使用默认参数：

| 输入 | 输出 |
|---|---|
| 视频：mp4 mov mkv webm avi m4v flv wmv | h265 编码的 `.mp4` |
| 音频：wav wma flac | `.m4a`（128k） |
| 音频：mp3 m4a aac ogg opus | 原格式，按 128k 重新编码 |
| 图片：jpg png webp avif | 原格式 |
| 图片：gif | `.webp`（保留动画） |
| 图片：bmp tif tiff heic heif | `.jpg` |
| pdf | `.pdf` |

### `info`

用 ffprobe 以 JSON 格式输出文件的流和容器信息。主要用于视频和音频，也能读常见图片，不支持 PDF。

## 已知限制

- **视频**
  - 按 ffmpeg 的默认规则选流，每种类型各保留一路，多音轨只保留一条。
  - 输出统一为 8 位 `yuv420p`，10 位和 HDR 视频会被转成 8 位。
  - 不显示进度，只有一个转圈动画。
- **低码率音频**：`auto` 会把 mp3、m4a 等有损音频按 128k 重新编码。原本码率就不高的文件，这样做只损失音质，体积省不了多少（结果变大时会被自动丢弃）。
- **PDF**
  - CMYK 图片、带透明蒙版（SMask）的图片、1 位和 16 位图片都会跳过，因为直接转换会偏色或出错。
  - 不处理字体和文字。
  - 有意不依赖 Ghostscript，没有额外的外部依赖。代价是压缩力度通常不如 `gs -dPDFSETTINGS=/ebook` 这类预设，例如不会精简字体。
- **串行处理**：批量处理时逐个文件进行。

## 开发

```bash
uv sync                                       # 包含 pytest、ruff 等开发依赖
uv run pytest                                 # 需要 ffmpeg 的测试，在没装 ffmpeg 时会自动跳过
uv run ruff check . && uv run ruff format .
```

代码结构和约定见 [CLAUDE.md](CLAUDE.md)。
