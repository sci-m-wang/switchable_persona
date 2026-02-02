#!/usr/bin/env python3
"""Build exact URL->local mapping by hashing remote media and local files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: str, exts: Tuple[str, ...]) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.lower().endswith(exts):
                yield os.path.join(dirpath, name)


def build_local_index(root: str, exts: Tuple[str, ...]) -> Dict[Tuple[int, str], str]:
    index: Dict[Tuple[int, str], str] = {}
    for path in iter_files(root, exts):
        try:
            size = os.path.getsize(path)
            digest = sha256_file(path)
            index[(size, digest)] = path
        except OSError:
            continue
    return index


def download_to_tmp(url: str) -> str:
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="media_dl_")
    os.close(tmp_fd)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return tmp_path


def extract_urls(weibo_json: str) -> Tuple[List[str], List[str]]:
    data = json.loads(Path(weibo_json).read_text(encoding="utf-8"))
    posts = data.get("weibo", [])
    img_urls: List[str] = []
    vid_urls: List[str] = []
    for item in posts:
        pics = item.get("original_pictures")
        if pics and pics != "无":
            for u in pics.split(","):
                u = u.strip()
                if u:
                    img_urls.append(u)
        vurl = item.get("video_url")
        if vurl and vurl != "无":
            vid_urls.append(vurl)
    return img_urls, vid_urls


def map_urls(urls: List[str], local_index: Dict[Tuple[int, str], str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for url in urls:
        try:
            tmp_path = download_to_tmp(url)
            size = os.path.getsize(tmp_path)
            digest = sha256_file(tmp_path)
            key = (size, digest)
            local = local_index.get(key)
            if local:
                mapping[url] = local
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Build URL->local media map")
    parser.add_argument("--weibo-json", required=True, help="Weibo JSON path")
    parser.add_argument("--media-root", required=True, help="Media root containing img/ and video/")
    parser.add_argument("--output", required=True, help="Output mapping JSON")
    parser.add_argument("--skip-video", action="store_true", help="Skip videos (large)")
    parser.add_argument("--skip-image", action="store_true", help="Skip images")

    args = parser.parse_args()

    img_urls, vid_urls = extract_urls(args.weibo_json)
    mapping = {"images": {}, "videos": {}}

    if not args.skip_image:
        img_root = os.path.join(args.media_root, "img")
        img_index = build_local_index(img_root, (".jpg", ".jpeg", ".png", ".webp"))
        mapping["images"] = map_urls(img_urls, img_index)

    if not args.skip_video:
        vid_root = os.path.join(args.media_root, "video")
        vid_index = build_local_index(vid_root, (".mp4", ".mov", ".mkv"))
        mapping["videos"] = map_urls(vid_urls, vid_index)

    Path(args.output).write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
