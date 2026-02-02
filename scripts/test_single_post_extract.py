#!/usr/bin/env python3
"""Test single-post extraction with Qwen3-VL via vLLM."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import List, Optional
from urllib.request import urlretrieve

from PIL import Image


DEFAULT_MODEL = "~/models/Qwen/Qwen3-VL-8B-Thinking"


SCHEMA_HINT = {
    "post_id": "string",
    "style": {
        "catchphrases": ["string"],
        "signature_patterns": ["string"],
        "tone": ["warm", "detailed"],
        "emotion": "positive|neutral|negative",
        "evidence": ["text span or visual cue"],
        "confidence": 0.0,
    },
    "safety_rewrite": {
        "terms": [{"term": "string", "replacement": "string"}],
        "evidence": ["text span"],
        "confidence": 0.0,
    },
    "stance": [
        {
            "target": "string",
            "position": "support|oppose|neutral",
            "reason": "string",
            "intent": "string",
            "evidence": ["text span or visual cue"],
            "confidence": 0.0,
        }
    ],
    "topic": {
        "trigger": "string",
        "one_sentence_summary": "string",
        "evidence": ["text span or visual cue"],
        "confidence": 0.0,
    },
    "knowledge_facts": [
        {"fact": "string", "evidence": ["text span"], "confidence": 0.0}
    ],
}


def _extract_video_frames(video_path: str, num_frames: int = 3) -> List[str]:
    """Extract a few frames via ffmpeg; return image file paths."""
    tmp_dir = tempfile.mkdtemp(prefix="vlm_frames_")
    out_pattern = os.path.join(tmp_dir, "frame_%02d.jpg")
    # Extract evenly spaced frames using fps filter as a simple heuristic.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        video_path,
        "-vf",
        f"fps={num_frames}",
        "-frames:v",
        str(num_frames),
        out_pattern,
    ]
    try:
        subprocess.check_call(cmd)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [os.path.join(tmp_dir, f"frame_{i:02d}.jpg") for i in range(1, num_frames + 1)]


def _download_media(urls: List[str], suffix: str) -> List[str]:
    tmp_dir = tempfile.mkdtemp(prefix="vlm_media_")
    local_paths: List[str] = []
    for idx, url in enumerate(urls, start=1):
        try:
            out_path = os.path.join(tmp_dir, f"media_{idx:02d}{suffix}")
            urlretrieve(url, out_path)
            local_paths.append(out_path)
        except Exception:
            continue
    return local_paths


def _find_by_basename(root: str, basenames: List[str]) -> List[str]:
    if not root or not os.path.isdir(root):
        return []
    found: List[str] = []
    for base in basenames:
        for dirpath, _, filenames in os.walk(root):
            if base in filenames:
                found.append(os.path.join(dirpath, base))
                break
    return found


def _load_images(image_path: Optional[str], video_path: Optional[str]) -> List[Image.Image]:
    images: List[Image.Image] = []
    if image_path:
        images.append(Image.open(image_path).convert("RGB"))
    if video_path:
        for frame_path in _extract_video_frames(video_path):
            try:
                images.append(Image.open(frame_path).convert("RGB"))
            except OSError:
                continue
    return images


def _select_post(weibo_json: str, post_id: Optional[str]) -> dict:
    data = json.loads(open(weibo_json, "r", encoding="utf-8").read())
    posts = data.get("weibo", [])
    if not posts:
        raise ValueError("No posts found in weibo JSON.")
    if post_id:
        for item in posts:
            if item.get("id") == post_id:
                return item
        raise ValueError(f"Post id {post_id} not found.")
    # Prefer a post with media
    for item in posts:
        if item.get("original_pictures") not in (None, "无") or item.get("video_url") not in (None, "无"):
            return item
    return posts[0]


def build_prompt(text: str, post_id: str) -> str:
    return (
        "You are a structured information extractor. "
        "Given a single social media post (text + optional visuals), "
        "return ONLY valid JSON matching the required schema. "
        "All fields must be present. Use empty lists/strings where unknown. "
        "Do NOT infer private attributes or medical/health info. "
        "Every extracted item must include evidence and confidence.\n\n"
        f"POST_ID: {post_id}\n"
        f"TEXT: {text}\n\n"
        "SCHEMA (for reference, not to be echoed):\n"
        f"{json.dumps(SCHEMA_HINT, ensure_ascii=False)}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-post extraction with Qwen3-VL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model path")
    parser.add_argument("--text", help="Post text (optional if --weibo-json is provided)")
    parser.add_argument("--post-id", default=None, help="Post ID (used with --weibo-json)")
    parser.add_argument("--weibo-json", help="Weibo JSON file from crawler")
    parser.add_argument("--image", help="Image path (local)")
    parser.add_argument("--video", help="Video path (local)")
    parser.add_argument("--max-images", type=int, default=3, help="Max images to load/download")
    parser.add_argument("--no-download-media", action="store_true", help="Skip downloading media URLs")
    parser.add_argument("--media-root", help="Local media root (contains img/ and video/)")
    parser.add_argument("--prefer-local-media", action="store_true", help="Prefer local media if found")
    parser.add_argument("--output", help="Output JSON file path")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=120000,
        help="Override model max length to fit KV cache on the GPU.",
    )
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.9,
        help="KV cache memory utilization ratio (0-1).",
    )

    args = parser.parse_args()

    model_path = os.path.expanduser(args.model)

    text = args.text
    post_id = args.post_id or "post-001"
    image_path = args.image
    video_path = args.video

    if args.weibo_json:
        post = _select_post(args.weibo_json, args.post_id)
        text = post.get("content", "")
        post_id = post.get("id", post_id)
        media_root = args.media_root
        if not media_root:
            media_root = os.path.join(os.path.dirname(args.weibo_json), "")
        img_root = os.path.join(media_root, "img")
        vid_root = os.path.join(media_root, "video")

        # Prefer embedded media mapping in JSON if present
        media = post.get("media") or {}
        if not image_path:
            media_imgs = media.get("original_pictures") or []
            if media_imgs:
                image_path = media_imgs[0].get("path")
        if not video_path:
            media_vids = media.get("video") or []
            if media_vids:
                video_path = media_vids[0].get("path")

        pics = post.get("original_pictures")
        if pics and pics != "无" and not image_path:
            urls = [u.strip() for u in pics.split(",") if u.strip()]
            bases = [os.path.basename(u) for u in urls]
            local_imgs = _find_by_basename(img_root, bases)
            if local_imgs and args.prefer_local_media:
                image_path = local_imgs[0]
            elif not args.no_download_media:
                dl_imgs = _download_media(urls[: args.max_images], ".jpg")
                if dl_imgs:
                    image_path = dl_imgs[0]

        vurl = post.get("video_url")
        if vurl and vurl != "无" and not video_path:
            base = os.path.basename(vurl)
            local_vids = _find_by_basename(vid_root, [base])
            if local_vids and args.prefer_local_media:
                video_path = local_vids[0]
            elif not args.no_download_media:
                dl_vids = _download_media([vurl], ".mp4")
                if dl_vids:
                    video_path = dl_vids[0]

    if not text:
        raise SystemExit("No text provided. Use --text or --weibo-json.")

    images = _load_images(image_path, video_path)

    # Ensure CUDA runtime (libcudart.so.12) from the venv is discoverable before importing vLLM.
    cuda_runtime = os.path.join(
        os.path.dirname(sys.executable),
        "..",
        "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages",
        "nvidia",
        "cuda_runtime",
        "lib",
    )
    cuda_runtime = os.path.abspath(cuda_runtime)
    if os.path.isdir(cuda_runtime):
        os.environ["LD_LIBRARY_PATH"] = f"{cuda_runtime}:{os.environ.get('LD_LIBRARY_PATH', '')}"

    from vllm import LLM, SamplingParams  # import after env is set

    llm = LLM(
        model=model_path,
        trust_remote_code=True,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
    )
    sampling_params = SamplingParams(temperature=args.temperature, max_tokens=args.max_tokens)

    prompt = build_prompt(text, post_id)

    multi_modal = None
    if images:
        multi_modal = [{"image": images}]  # list of PIL images

    outputs = llm.generate([prompt], sampling_params, multi_modal_data=multi_modal)
    text_out = outputs[0].outputs[0].text.strip()

    # Best-effort JSON cleanup
    json_start = text_out.find("{")
    json_end = text_out.rfind("}")
    if json_start != -1 and json_end != -1:
        text_out = text_out[json_start : json_end + 1]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text_out)
    else:
        print(text_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
