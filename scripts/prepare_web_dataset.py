#!/usr/bin/env python3
"""Prepare a Vercel-friendly dataset file for the annotation web.

Typical pipeline output (see scripts/extract_all_weibo.py) is JSONL where each
line looks like:

  {"meta": {...}, "input": {...}, "result": {"post_id":..., "extraction":..., "media_used": {...}}}

The annotation web can load that JSONL directly.

However, media_used paths are usually local disk paths. Vercel cannot access
local files, so you should upload media to a public host (CDN / object storage)
and rewrite those paths to http(s) URLs.

Example:
  python3 scripts/prepare_web_dataset.py \
    --input processed_data/extractions.jsonl \
    --output out/extractions.public.jsonl \
    --local-weibo-prefix /abs/path/to/weibo \
    --media-base-url https://cdn.example.com/weibo

Then upload out/extractions.public.jsonl somewhere public and load it by URL in the web UI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _is_http(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _join_url(base: str, rel: str) -> str:
    base = base.rstrip("/")
    rel = rel.lstrip("/")
    return f"{base}/{rel}"


def _rewrite_path(p: str, local_prefix: str, base_url: str) -> str:
    raw = (p or "").strip()
    if not raw:
        return raw
    if _is_http(raw):
        return raw

    rel = None
    if local_prefix and raw.startswith(local_prefix):
        rel = raw[len(local_prefix) :]

    if rel is None:
        norm = raw
        if norm.startswith("./"):
            norm = norm[2:]
        if norm.startswith("weibo/"):
            rel = norm

    if rel is None:
        # Leave untouched if we cannot map it.
        return raw

    rel = rel.lstrip("/")
    if base_url.rstrip("/").endswith("/weibo") and rel.startswith("weibo/"):
        rel = rel[len("weibo/") :]

    return _join_url(base_url, rel)


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main() -> int:
    ap = argparse.ArgumentParser(description="Rewrite media paths in extractions.jsonl for web deployment")
    ap.add_argument("--input", required=True, help="Input JSONL (e.g. processed_data/extractions.jsonl)")
    ap.add_argument("--output", required=True, help="Output JSONL")
    ap.add_argument("--local-weibo-prefix", default="", help="Prefix to strip from absolute media paths")
    ap.add_argument("--media-base-url", default="", help="Base URL hosting weibo media, e.g. https://cdn.example.com/weibo")
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    local_prefix = args.local_weibo_prefix.strip()
    base_url = args.media_base_url.strip()

    if not base_url:
        raise SystemExit("--media-base-url is required to rewrite local media paths to http(s) URLs")

    n_in = 0
    n_out = 0

    with out.open("w", encoding="utf-8") as fo:
        for rec in _iter_jsonl(inp):
            n_in += 1
            result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
            media = result.get("media_used") if isinstance(result.get("media_used"), dict) else {}

            def rw_list(xs):
                if not isinstance(xs, list):
                    return []
                out_x = []
                for x in xs:
                    if not isinstance(x, str):
                        continue
                    out_x.append(_rewrite_path(x, local_prefix, base_url))
                return out_x

            if isinstance(media, dict):
                media["images"] = rw_list(media.get("images"))
                media["videos"] = rw_list(media.get("videos"))
                result["media_used"] = media
                rec["result"] = result

            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_out += 1

    print(f"[prepare_web_dataset] in={n_in} out={n_out} wrote={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
