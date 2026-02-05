# switchable_persona

## 数据备份（大数据不进 Git）

- 推荐阅读： [docs/data_backup.md](docs/data_backup.md)
- 一键打包：`bash scripts/backup_data.sh weibo processed_data`
- 一键恢复：`bash scripts/restore_data.sh backups/<timestamp>`

这套方案用于把爬取/分析数据从代码仓库剥离出来：代码照常同步 GitHub，但数据用归档分卷备份到外部存储（GitHub Releases/私有数据仓库/云盘）。

## 标注页面（Vercel 免费版部署）

仓库新增了一个 Next.js 前端（纯浏览器保存 + 导出 JSON），适配 Vercel 的主流模板部署方式：

- 前端目录：`web/`
- Vercel 上创建项目时，把 **Root Directory** 设置为 `web`
- 构建命令：`npm run build`
- 输出：Next.js 默认（Vercel 可自动识别）

本前端默认不包含后端存储（避免免费平台数据库依赖），标注数据保存在浏览器 localStorage，并支持导出/导入 JSON。

### 为什么不把完整微博/媒体数据直接提交到 GitHub？

- GitHub 有单文件 100MB 限制，且把 `weibo/` 这类大目录直接进 Git 历史会导致 push 失败、仓库极其臃肿。
- Git LFS 即使可用，Vercel 构建通常拿不到真实 LFS 内容（常见情况是只拿到 pointer），不适合作为部署数据源。

推荐做法：代码仓库保持轻量；把完整数据放到外部存储（Releases/云盘/对象存储），标注页通过 URL 加载任务文件（JSON/JSONL）。

### 真实数据 + 媒体如何在 Vercel 上显示？

抽取结果里的 `result.media_used` 往往是本地路径（例如 `/.../weibo/...` 或 `weibo/...`）。Vercel 访问不到本地文件，需要：

- 把 `weibo/` 里的媒体上传到公开存储（CDN/对象存储）
- 用脚本把路径改写成 URL：`python3 scripts/prepare_web_dataset.py --input processed_data/extractions.jsonl --output out/extractions.public.jsonl --media-base-url https://cdn.example.com/weibo`
- 或者在标注页里填写“Media Base URL / Local Weibo Prefix”让前端实时映射

This project hosts a Python 3.13 environment for future VLM work (vLLM + VL models).
Note: vLLM officially documents Python 3.10–3.13, but 3.14 works with current wheels.

## Next steps
- Create a virtual environment: `UV_CACHE_DIR=/tmp/uv-cache uv venv --python 3.13 .venv`
- Install/sync core deps (CUDA 13 wheels from the official PyTorch index):
  - `UV_CACHE_DIR=/tmp/uv-cache uv sync --extra vlm`
