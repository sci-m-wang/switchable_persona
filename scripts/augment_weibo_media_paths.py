#!/usr/bin/env python3
"""Augment weibo JSON with local media paths based on crawler naming rules."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _infer_image_paths(media_root: str, publish_time: str, post_id: str, urls: list[str]) -> list[dict]:
    if not publish_time or not post_id:
        return []
    date_prefix = publish_time[:10].replace("-", "")
    base_prefix = f"{date_prefix}_{post_id}"
    candidates = []
    for idx, url in enumerate(urls, start=1):
        ext = os.path.splitext(url)[1]
        if not ext or len(ext) > 5:
            ext = ".jpg"
        name = f"{base_prefix}_{idx}{ext}" if len(urls) > 1 else f"{base_prefix}{ext}"
        candidates.append((url, name))

    found = []
    for url, name in candidates:
        for sub in ("原创微博图片", "转发微博图片"):
            path = os.path.join(media_root, "img", sub, name)
            if os.path.isfile(path):
                found.append({"url": url, "path": path})
                break
    return found


def _infer_video_paths(media_root: str, publish_time: str, post_id: str, url: str) -> list[dict]:
    if not publish_time or not post_id or not url:
        return []
    date_prefix = publish_time[:10].replace("-", "")
    base_prefix = f"{date_prefix}_{post_id}.mp4"
    path = os.path.join(media_root, "video", base_prefix)
    if os.path.isfile(path):
        return [{"url": url, "path": path}]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Augment weibo JSON with local media paths")
    parser.add_argument("--weibo-json", required=True, help="Weibo JSON path")
    parser.add_argument("--media-root", required=True, help="Media root containing img/ and video/")
    parser.add_argument("--output", help="Output JSON path (defaults to in-place)")
    args = parser.parse_args()

    data = json.loads(Path(args.weibo_json).read_text(encoding="utf-8"))
    posts = data.get("weibo", [])
    for item in posts:
        item.setdefault("media", {"original_pictures": [], "retweet_pictures": [], "video": []})
        publish_time = item.get("publish_time", "")
        post_id = item.get("id", "")

        pics = item.get("original_pictures")
        if pics and pics != "无":
            urls = [u.strip() for u in pics.split(",") if u.strip()]
            mapped = _infer_image_paths(args.media_root, publish_time, post_id, urls)
            if mapped:
                item["media"]["original_pictures"] = mapped

        rpics = item.get("retweet_pictures")
        if rpics and rpics != "无":
            urls = [u.strip() for u in rpics.split(",") if u.strip()]
            mapped = _infer_image_paths(args.media_root, publish_time, post_id, urls)
            if mapped:
                item["media"]["retweet_pictures"] = mapped

        vurl = item.get("video_url")
        if vurl and vurl != "无":
            mapped = _infer_video_paths(args.media_root, publish_time, post_id, vurl)
            if mapped:
                item["media"]["video"] = mapped

    out_path = args.output or args.weibo_json
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
