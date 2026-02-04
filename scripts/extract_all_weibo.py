#!/usr/bin/env python3
"""Batch extraction for all weibo JSON files under a root directory."""

from __future__ import annotations

import argparse
import json
import os
import site
import sys
import tempfile
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.request import urlretrieve

import ctypes
from transformers import AutoProcessor
from qwen_vl_utils import process_vision_info

from vllm import LLM, SamplingParams
from vllm.sampling_params import StructuredOutputsParams

DEFAULT_MODEL = "~/models/Qwen/Qwen3-VL-8B-Thinking"

SCHEMA_JSON = {
    "type": "object",
    "additionalProperties": False,
    "required": ["post_id", "style", "safety_rewrite", "stance", "topic", "knowledge_facts"],
    "properties": {
        "post_id": {"type": "string"},
        "style": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "catchphrases",
                "signature_patterns",
                "tone",
                "emotion",
                "evidence",
                "confidence",
            ],
            "properties": {
                "catchphrases": {"type": "array", "items": {"type": "string"}},
                "signature_patterns": {"type": "array", "items": {"type": "string"}},
                "tone": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "formal",
                            "casual",
                            "celebratory",
                            "persuasive",
                            "objective",
                            "humorous",
                            "sarcastic",
                            "empathetic",
                            "authoritative",
                            "promotional",
                            "instructional",
                            "narrative",
                            "urgent",
                            "reflective",
                        ],
                    },
                },
                "emotion": {
                    "type": "string",
                    "enum": [
                        "joy",
                        "trust",
                        "fear",
                        "surprise",
                        "sadness",
                        "disgust",
                        "anger",
                        "anticipation",
                        "none",
                    ],
                },
                "evidence": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
        },
        "safety_rewrite": {
            "type": "object",
            "additionalProperties": False,
            "required": ["terms", "evidence", "confidence"],
            "properties": {
                "terms": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["term", "replacement"],
                        "properties": {
                            "term": {"type": "string"},
                            "replacement": {"type": "string"},
                        },
                    },
                },
                "evidence": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
        },
        "stance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["targets", "reasoning"],
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["target", "position", "evidence", "confidence"],
                        "properties": {
                            "target": {"type": "string"},
                            "position": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "number"},
                        },
                    },
                },
                "reasoning": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "target",
                            "opinion",
                            "intent",
                            "evidence",
                            "confidence",
                        ],
                        "properties": {
                            "target": {"type": "string"},
                            "opinion": {"type": "string"},
                            "intent": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                            "confidence": {"type": "number"},
                        },
                    },
                },
            },
        },
        "topic": {
            "type": "object",
            "additionalProperties": False,
            "required": ["trigger", "one_sentence_summary", "evidence", "confidence"],
            "properties": {
                "trigger": {"type": "string"},
                "one_sentence_summary": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
        },
        "knowledge_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fact", "evidence", "confidence"],
                "properties": {
                    "fact": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
    },
}


def build_user_text(text: str, post_id: str) -> str:
    return (
        "你是信息抽取器，服务于“基于三层人格架构构建虚拟角色”的长期任务。"
        "你的输出将直接用于驱动虚拟角色的行为、写作风格与记忆库。"
        "请基于单条微博（文字+图像/视频）做精确抽取，输出必须为严格 JSON。"
        "不得输出分析过程或多余文本。\n\n"
        "核心目标（与你的字段定义直接对应）：\n"
        "A) style：提取“发帖风格线索”。tone 不是情感极性，必须描述说话语气与风格"
        "（如 formal/casual/celebratory/persuasive/objective 等），可多选 1-3 个。"
        "emotion 使用 8 大情绪（joy/trust/fear/surprise/sadness/disgust/anger/anticipation），"
        "若无明显情绪则为 none。\n"
        "B) stance：抽取作者对“具体目标对象”的立场与观点，并说明其背后意图。"
        "必须拆成两层：targets（目标+立场+证据）与 reasoning（观点+意图+证据）。\n"
        "C) topic：等价于“发帖原因/触发事件/主题”，用于驱动虚拟角色发帖的动机描述，"
        "要求一句话概括，直接描述“因为什么而发帖”。\n"
        "D) knowledge_facts：用于构建虚拟角色的“经历/认知/记忆库”。只记录稳定的实体或长期事实"
        "（人/组织/品牌/物品/长期偏好/价值取向）。不要写一次性事件、短期里程碑或时间点。\n"
        "E) safety_rewrite：不是审查，而是“表达时可替换的敏感词/表述”（若无则空）。\n\n"
        "通用抽取原则：\n"
        "1) 只抽取文本或图像/视频中可直接支持的内容；不要主观脑补。\n"
        "2) 若某项不存在或不明显，保持为空列表/空字符串，confidence=0。\n"
        "3) 证据字段必须为原文或视觉线索的最小片段。\n"
        "4) 不要把“发帖原因”误放入 knowledge_facts；它应归入 topic。\n"
        "5) knowledge_facts 里只保留“长期可复用的事实/实体”。\n\n"
        f"POST_ID: {post_id}\n"
        f"TEXT: {text}\n\n"
        "输出 JSON schema（仅供参考，不要复述）：\n"
        f"{json.dumps(SCHEMA_JSON, ensure_ascii=False)}\n"
    )


def _download_media(urls: list[str], suffix: str) -> list[str]:
    tmp_dir = tempfile.mkdtemp(prefix="vlm_media_")
    local_paths: list[str] = []
    for idx, url in enumerate(urls, start=1):
        try:
            out_path = os.path.join(tmp_dir, f"media_{idx:02d}{suffix}")
            urlretrieve(url, out_path)
            local_paths.append(out_path)
        except Exception:
            continue
    return local_paths


def _find_by_basename(root: str, basenames: list[str]) -> list[str]:
    if not root or not os.path.isdir(root):
        return []
    found: list[str] = []
    for base in basenames:
        for dirpath, _, filenames in os.walk(root):
            if base in filenames:
                found.append(os.path.join(dirpath, base))
                break
    return found


def _as_file_uri(path: str) -> str:
    if path.startswith(("file://", "http://", "https://", "data:")):
        return path
    return f"file://{path}"


def _ensure_cuda_runtime() -> None:
    cuda_lib_dirs = []
    cuda_runtime_lib = None
    for sp in site.getsitepackages():
        candidate = os.path.join(sp, "nvidia", "cuda_runtime", "lib")
        if os.path.isdir(candidate):
            cuda_lib_dirs.append(candidate)
            cand_lib = os.path.join(candidate, "libcudart.so.12")
            if os.path.isfile(cand_lib) and cuda_runtime_lib is None:
                cuda_runtime_lib = cand_lib
    if cuda_lib_dirs:
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = ":".join(cuda_lib_dirs + ([existing] if existing else []))
    if cuda_runtime_lib and os.environ.get("CUDA_PRELOAD_DONE") != "1":
        env = dict(os.environ)
        env["CUDA_PRELOAD_DONE"] = "1"
        env["LD_PRELOAD"] = f"{cuda_runtime_lib}:{env.get('LD_PRELOAD', '')}".rstrip(":")
        os.execve(sys.executable, [sys.executable] + sys.argv, env)
    if cuda_runtime_lib:
        try:
            ctypes.CDLL(cuda_runtime_lib, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass


def _iter_weibo_jsons(root: str) -> Iterable[str]:
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".json"):
                yield os.path.join(dirpath, name)


def _select_media_paths(post: dict, media_root: str, max_images: int, allow_download: bool) -> tuple[list[str], list[str]]:
    image_paths: list[str] = []
    video_paths: list[str] = []

    media = post.get("media") or {}
    media_imgs = media.get("original_pictures") or []
    if media_imgs:
        for item in media_imgs[:max_images]:
            path = item.get("path")
            if path and os.path.isfile(path):
                image_paths.append(path)
    media_vids = media.get("video") or []
    if media_vids:
        for item in media_vids:
            path = item.get("path")
            if path and os.path.isfile(path):
                video_paths.append(path)

    if not image_paths:
        pics = post.get("original_pictures")
        if pics and pics != "无":
            urls = [u.strip() for u in pics.split(",") if u.strip()]
            bases = [os.path.basename(u) for u in urls]
            local_imgs = _find_by_basename(os.path.join(media_root, "img"), bases)
            image_paths = local_imgs[:max_images]
            if not image_paths and allow_download:
                image_paths = _download_media(urls[:max_images], ".jpg")

    if not video_paths:
        vurl = post.get("video_url")
        if vurl and vurl != "无":
            base = os.path.basename(vurl)
            local_vids = _find_by_basename(os.path.join(media_root, "video"), [base])
            video_paths = local_vids
            if not video_paths and allow_download:
                video_paths = _download_media([vurl], ".mp4")

    return image_paths, video_paths


def _extract_one(
    llm: LLM,
    processor: AutoProcessor,
    sampling_params: SamplingParams,
    post: dict,
    media_root: str,
    max_images: int,
    allow_download: bool,
    skip_videos: bool,
    bad_videos: list[dict],
) -> dict:
    text = post.get("content", "")
    post_id = post.get("id", "")

    images, videos = _select_media_paths(post, media_root, max_images, allow_download)
    if skip_videos:
        videos = []
    user_text = build_user_text(text, post_id)

    messages: list[dict] = [
        {
            "role": "system",
            "content": "Return ONLY valid JSON. Do not include any extra text.",
        },
        {
            "role": "user",
            "content": (
                [{"type": "image", "image": _as_file_uri(path)} for path in images]
                + [{"type": "video", "video": _as_file_uri(path)} for path in videos]
                + [{"type": "text", "text": user_text}]
            ),
        },
    ]

    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    try:
        image_inputs, video_inputs, video_kwargs = process_vision_info(
            messages,
            image_patch_size=processor.image_processor.patch_size,
            return_video_kwargs=True,
            return_video_metadata=True,
        )
    except Exception as exc:
        # If video decoding fails, retry with images only.
        if videos:
            for path in videos:
                bad_videos.append(
                    {
                        "post_id": post_id,
                        "video_path": path,
                        "error": str(exc),
                        "weibo_media_root": media_root,
                    }
                )
            print(f"[warn] video decode failed for post {post_id}: {exc}", file=sys.stderr)
            videos = []
            messages = [
                {
                    "role": "system",
                    "content": "Return ONLY valid JSON. Do not include any extra text.",
                },
                {
                    "role": "user",
                    "content": (
                        [{"type": "image", "image": _as_file_uri(path)} for path in images]
                        + [{"type": "text", "text": user_text}]
                    ),
                },
            ]
            prompt = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            image_inputs, video_inputs, video_kwargs = process_vision_info(
                messages,
                image_patch_size=processor.image_processor.patch_size,
                return_video_kwargs=True,
                return_video_metadata=True,
            )
        else:
            raise
    mm_data: dict = {}
    if image_inputs is not None:
        mm_data["image"] = image_inputs
    if video_inputs is not None:
        mm_data["video"] = video_inputs

    inputs = [
        {
            "prompt": prompt,
            "multi_modal_data": mm_data,
            "mm_processor_kwargs": video_kwargs,
        }
    ]

    outputs = llm.generate(inputs, sampling_params)
    text_out = ""
    if outputs and outputs[0].outputs:
        text_out = outputs[0].outputs[0].text.strip()
    if not text_out:
        pieces = []
        for out in outputs or []:
            for cand in out.outputs:
                if cand.text:
                    pieces.append(cand.text)
        text_out = "".join(pieces).strip()
    try:
        parsed = json.loads(text_out)
    except json.JSONDecodeError:
        parsed = {"_raw": text_out}
    return {
        "post_id": post_id,
        "extraction": parsed,
        "media_used": {"images": images, "videos": videos},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch extract all weibo posts under a root")
    parser.add_argument("--weibo-root", required=True, help="Root dir that contains weibo JSON folders")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model path")
    parser.add_argument("--output", default="processed_data/extractions.jsonl")
    parser.add_argument("--output-dir", default="processed_data/extractions")
    parser.add_argument("--max-images", type=int, default=3)
    parser.add_argument("--allow-download-media", action="store_true")
    parser.add_argument("--skip-videos", action="store_true", help="Skip video inputs if decoding is unstable")
    parser.add_argument("--bad-video-log", default="processed_data/bad_videos.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-model-len", type=int, default=110000)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1200)
    args = parser.parse_args()

    _ensure_cuda_runtime()

    model_path = os.path.expanduser(args.model)
    llm = LLM(
        model=model_path,
        trust_remote_code=True,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
    )
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    sampling_params = SamplingParams(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        structured_outputs=StructuredOutputsParams(json=SCHEMA_JSON),
    )

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    processed = set()
    if args.resume:
        if os.path.isfile(args.output):
            with open(args.output, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        processed.add(rec.get("post_id"))
                    except json.JSONDecodeError:
                        continue

    total = 0
    bad_videos: list[dict] = []
    with open(args.output, "a", encoding="utf-8") as out:
        for weibo_json in _iter_weibo_jsons(args.weibo_root):
            data = json.loads(open(weibo_json, "r", encoding="utf-8").read())
            posts = data.get("weibo", [])
            media_root = os.path.dirname(weibo_json)
            for post in posts:
                post_id = post.get("id", "")
                if not post_id:
                    continue
                if args.resume and post_id in processed:
                    continue
                record = _extract_one(
                    llm,
                    processor,
                    sampling_params,
                    post,
                    media_root,
                    args.max_images,
                    args.allow_download_media,
                    args.skip_videos,
                    bad_videos,
                )
                meta = {
                    "post_id": post_id,
                    "weibo_json": weibo_json,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "model": model_path,
                    "publish_time": post.get("publish_time"),
                }
                line = {"meta": meta, "input": post, "result": record}
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
                with open(
                    os.path.join(args.output_dir, f"{post_id}.json"),
                    "w",
                    encoding="utf-8",
                ) as fp:
                    json.dump(line, fp, ensure_ascii=False, indent=2)
                total += 1
                if args.limit and total >= args.limit:
                    return 0
    if bad_videos:
        os.makedirs(os.path.dirname(args.bad_video_log), exist_ok=True)
        with open(args.bad_video_log, "a", encoding="utf-8") as f:
            for item in bad_videos:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
