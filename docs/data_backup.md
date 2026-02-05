# 数据备份方案（爬取/分析数据，不进 GitHub 仓库）

这个仓库已经把 `weibo/`、`processed_data/`、`docs/build/` 等大目录从 Git 历史中移除，避免 GitHub push 失败与泄露风险。

但你仍然需要“备份数据”。推荐的做法是：

- 数据仍保存在本地磁盘（或外部盘）
- 用脚本打包成可校验的归档（可分卷）
- 把归档上传到**独立的存储**（例如：GitHub Releases、单独的私有数据仓库、云盘/对象存储）
- 在代码仓库里只保存：
  - 备份脚本
  - 校验信息（SHA256）
  - 数据格式说明/恢复步骤

## 1) 一键打包（推荐）

在仓库根目录：

```bash
bash scripts/backup_data.sh weibo processed_data
```

- 输出目录：`backups/<timestamp>/`
- 默认会生成：
  - `data.tar.zst`（zstd 压缩 tar 包）
  - `data.tar.zst.part-*`（分卷，便于上传；默认每卷约 1900MiB）
  - `SHA256SUMS`（校验文件）
  - `manifest.json`（包含 git commit、打包内容、时间等）

如果目录不存在（例如你本机没有 `processed_data/`），脚本会跳过并给出提示。

## 2) 上传到哪里？

你有三种常见选择：

1. **GitHub Releases（推荐）**
   - 优点：和代码仓库绑定、下载方便
   - 缺点：单个资产有大小限制（所以脚本默认分卷）

2. **单独的私有数据仓库（可用 Git LFS）**
   - 优点：版本化、权限隔离
   - 缺点：要额外维护一个 repo；LFS 对大规模媒体也可能有配额压力

3. **云盘/对象存储（S3/OSS/WebDAV 等）**
   - 优点：成本可控、容量大
   - 缺点：需要你自己管理权限和链接

## 3) 恢复数据

把分卷文件放回同一个目录后：

```bash
bash scripts/restore_data.sh backups/<timestamp>
```

脚本会：

- 合并分卷
- 校验 SHA256
- 解压到仓库根目录（还原 `weibo/`、`processed_data/` 等）

## 4) 安全提醒（重要）

- 如果任何 secret 曾经被提交到 GitHub/其他远端，即使后来清理了历史，也应当**轮换/作废**对应密钥。
- 不要把 `annotator_secret.txt`、账号密码、token 等放入公开仓库。

