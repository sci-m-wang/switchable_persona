#!/usr/bin/env python3
"""Minimal annotation web app with login/consent/questionnaires/annotation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi import status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("ANNOTATION_DATA_DIR", ROOT / "processed_data"))
WEIBO_ROOT = Path(os.environ.get("WEIBO_ROOT", ROOT / "weibo")).resolve()
ACCOUNTS_FILE = DATA_DIR / "annotator_accounts.json"
SECRET_FILE = DATA_DIR / "annotator_secret.txt"
ANNOTATIONS_FILE = DATA_DIR / "annotations.json"
EXTRACTIONS_DIR = DATA_DIR / "extractions"
EXTRACTIONS_JSONL = DATA_DIR / "extractions.jsonl"
QUESTIONNAIRES_DIR = ROOT / "questionnaires"

app = FastAPI()

# Cookie session TTL. If the annotator is idle beyond this window,
# they'll be asked to log in again.
SESSION_TTL_SECONDS = int(os.environ.get("ANNOTATION_SESSION_TTL_SECONDS", str(12 * 3600)))


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)

def _ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ACCOUNTS_FILE.exists():
        ACCOUNTS_FILE.write_text(
            json.dumps(
                {
                    "users": [
                        {"username": "annotator1", "password": "changeme"},
                        {"username": "annotator2", "password": "changeme"},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(os.urandom(32).hex(), encoding="utf-8")
    if not ANNOTATIONS_FILE.exists():
        ANNOTATIONS_FILE.write_text("{}", encoding="utf-8")


def _get_secret() -> bytes:
    _ensure_data_files()
    return SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")


def _sign(value: str) -> str:
    secret = _get_secret()
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _make_session(username: str) -> str:
    ts = str(int(time.time()))
    payload = f"{username}|{ts}"
    sig = _sign(payload)
    raw = f"{payload}|{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _parse_session(token: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, ts, sig = raw.split("|", 2)
    except Exception:
        return None
    try:
        ts_i = int(ts)
    except ValueError:
        return None
    if int(time.time()) - ts_i > SESSION_TTL_SECONDS:
        return None
    payload = f"{username}|{ts}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    return username


def _load_accounts() -> Dict[str, str]:
    _ensure_data_files()
    data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    return {u["username"]: u["password"] for u in data.get("users", [])}


def _load_questionnaires() -> List[Dict[str, Any]]:
    files = [
        "16Personalities.json",
        "BFI.json",
        "PVQ.json",
        "EIS.json",
        "LMS.json",
    ]
    questionnaires: List[Dict[str, Any]] = []
    for name in files:
        path = QUESTIONNAIRES_DIR / name
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            key = (
                raw.get("name")
                or raw.get("id")
                or raw.get("title")
                or raw.get("full_name")
                or path.stem
            )
            title = raw.get("full_name") or raw.get("title") or raw.get("name") or path.stem
            instructions = (
                raw.get("psychobench_prompt_choice_instruction")
                or raw.get("instructions")
                or raw.get("psychobench_prompt")
                or ""
            )

            if "range" in raw and isinstance(raw["range"], list) and len(raw["range"]) == 2:
                scale_min, scale_max = int(raw["range"][0]), int(raw["range"][1])
            elif "response_scale" in raw and isinstance(raw["response_scale"], dict):
                scale_min = int(raw["response_scale"].get("min", 1))
                scale_max = int(raw["response_scale"].get("max", 7))
            else:
                scale_min, scale_max = 1, 7

            labels = None
            if (
                "response_scale" in raw
                and isinstance(raw["response_scale"], dict)
                and isinstance(raw["response_scale"].get("labels"), list)
            ):
                labels = [str(x) for x in raw["response_scale"]["labels"]]

            items: List[Dict[str, Any]] = []
            if "questions" in raw and isinstance(raw["questions"], dict):
                for qid, qitem in raw["questions"].items():
                    text = (
                        qitem.get("rewritten_zh")
                        or qitem.get("origin_zh")
                        or qitem.get("origin_en")
                        or ""
                    )
                    item = {"id": str(qid), "text": text}
                    if isinstance(qitem.get("options"), dict):
                        item["options"] = qitem["options"]
                    if labels:
                        item["labels"] = labels
                    items.append(item)
            elif "items" in raw and isinstance(raw["items"], list):
                for it in raw["items"]:
                    qid = it.get("id") or it.get("qid") or it.get("key")
                    text = it.get("text") or it.get("origin_zh") or it.get("origin_en") or ""
                    item = {"id": str(qid), "text": text}
                    if labels:
                        item["labels"] = labels
                    items.append(item)

            questionnaires.append(
                {
                    "key": str(key),
                    "title": str(title),
                    "instructions": str(instructions),
                    "scale_min": scale_min,
                    "scale_max": scale_max,
                    "items": items,
                }
            )
    return questionnaires


def _load_extractions() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if EXTRACTIONS_DIR.exists():
        for item in sorted(EXTRACTIONS_DIR.glob("*.json")):
            try:
                records.append(json.loads(item.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    elif EXTRACTIONS_JSONL.exists():
        with EXTRACTIONS_JSONL.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _load_annotations() -> Dict[str, Any]:
    _ensure_data_files()
    return json.loads(ANNOTATIONS_FILE.read_text(encoding="utf-8"))


def _save_annotations(data: Dict[str, Any]) -> None:
    ANNOTATIONS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_user_state(username: str) -> Dict[str, Any]:
    data = _load_annotations()
    if username not in data:
        data[username] = {
            "consent": False,
            "questionnaires": {},
            "progress_index": 0,
            "annotations": {},
        }
        _save_annotations(data)
    return data[username]


def _save_user_state(username: str, state: Dict[str, Any]) -> None:
    data = _load_annotations()
    data[username] = state
    _save_annotations(data)


def _questionnaires_complete(state: Dict[str, Any]) -> bool:
    filled = state.get("questionnaires") or {}
    required = _load_questionnaires()
    for q in required:
        ans = filled.get(q["key"]) or {}
        if not isinstance(ans, dict):
            return False
        if len(ans) < len(q.get("items") or []):
            return False
    return True


def get_current_user(request: Request) -> str:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401)
    user = _parse_session(token)
    if not user:
        raise HTTPException(status_code=401)
    return user


def _html_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 24px; line-height: 1.5; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
    textarea {{ width: 100%; height: 320px; font-family: ui-monospace, monospace; }}
    input[type="text"], input[type="password"] {{ width: 280px; padding: 6px; }}
    button {{ padding: 6px 10px; }}
    .muted {{ color: #666; font-size: 13px; }}
    .row {{ display:flex; gap:12px; flex-wrap: wrap; align-items: center; }}
    .pill {{ display:inline-block; border:1px solid #eee; border-radius:999px; padding:2px 10px; margin-right:6px; }}
    .media img {{ max-width: 240px; margin: 6px; border: 1px solid #ddd; }}
    .media video {{ max-width: 360px; margin: 6px; border: 1px solid #ddd; }}
  </style>
</head>
<body>
{body}
</body>
</html>"""
    )


@app.get("/", response_class=RedirectResponse)
def index(request: Request):
    try:
        user = get_current_user(request)
    except HTTPException:
        return RedirectResponse("/login")
    state = _get_user_state(user)
    if not state.get("consent"):
        return RedirectResponse("/consent")
    if not _questionnaires_complete(state):
        return RedirectResponse("/questionnaires")
    return RedirectResponse("/annotate")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _html_page(
        "Login",
        """
<h1>标注者登录</h1>
<form method="post" action="/login">
  <div><label>用户名: <input type="text" name="username" /></label></div>
  <div><label>密码: <input type="password" name="password" /></label></div>
  <div style="margin-top:12px;"><button type="submit">登录</button></div>
</form>
""",
    )


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    accounts = _load_accounts()
    if accounts.get(username) != password:
        return _html_page("Login Failed", "<p>用户名或密码错误</p>")
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(
        "session",
        _make_session(username),
        httponly=True,
        max_age=SESSION_TTL_SECONDS,
        samesite="lax",
    )
    return resp


@app.get("/logout", response_class=RedirectResponse)
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp


@app.get("/consent", response_class=HTMLResponse)
def consent_page(request: Request, user: str = Depends(get_current_user)):
    state = _get_user_state(user)
    checked = "checked" if state.get("consent") else ""
    signed_name = state.get("consent_signed_name", "")
    return _html_page(
        "Consent",
        f"""
<h1>协议确认</h1>
<div class="card">
<p><b>《内容授权与标注协议》</b></p>
<p>本协议用于：微博内容发表者（下称“授权人/标注者”）授权其内容用于研究与虚拟角色建模，并对抽取结果进行标注校正。</p>
<p><b>1. 授权内容</b>：你授权研究方在本项目范围内处理你导入的微博文本、图片、视频、链接与元数据（发布时间、互动量等）。</p>
<p><b>2. 使用目的</b>：仅用于科研与系统开发（包括：三层人格架构的角色建模、抽取/生成模型训练与评估、数据质量分析）。</p>
<p><b>3. 标注与量表</b>：你将填写量表并对系统抽取结果进行“确认/修改/补充”。标注数据用于提高抽取质量与角色一致性。</p>
<p><b>4. 隐私与安全</b>：研究方将采取合理措施限制访问。对外展示/分享将尽量去标识化（移除账号、链接、可识别信息）。</p>
<p><b>5. 撤回</b>：你可随时要求停止新增处理与新增使用；已产生的去标识化统计结果可能无法完全回滚。</p>
<p><b>6. 风险提示</b>：模型抽取可能存在误读；量表不构成医疗/法律建议。</p>
<p><b>7. 确认</b>：你确认你有权授权上述内容，并同意上述处理方式。</p>
</div>
<form method="post" action="/consent">
  <div class="card">
    <label><input type="checkbox" name="agree" value="yes" {checked}/> 我同意上述协议</label>
    <div style="margin-top:10px;">
      <label>签名（姓名/昵称）: <input type="text" name="signed_name" value="{signed_name}" /></label>
    </div>
  </div>
  <div style="margin-top:12px;"><button type="submit">继续</button></div>
</form>
""",
    )


@app.post("/consent")
def consent_submit(
    agree: Optional[str] = Form(None),
    signed_name: str = Form(""),
    user: str = Depends(get_current_user),
):
    state = _get_user_state(user)
    state["consent"] = bool(agree)
    state["consent_signed_name"] = signed_name.strip()
    state["consent_signed_at"] = None
    if state["consent"]:
        # signed_name is optional but recommended
        state["consent_signed_at"] = time.time()
    _save_user_state(user, state)
    return RedirectResponse("/questionnaires", status_code=302)


def _render_item_options(q: Dict[str, Any], item: Dict[str, Any], saved: Optional[str]) -> str:
    # Per-item discrete options.
    if isinstance(item.get("options"), dict) and item["options"]:
        opts = []
        for val, meta in sorted(
            item["options"].items(),
            key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else str(kv[0]),
        ):
            label = meta.get("zh") or meta.get("en") or str(val)
            checked = "checked" if saved is not None and str(saved) == str(val) else ""
            opts.append(
                f"<label style='display:block; margin:6px 0;'>"
                f"<input type='radio' name='q:{q['key']}:{item['id']}' value='{val}' {checked}/> "
                f"{val}. {label}</label>"
            )
        return "".join(opts)

    labels = item.get("labels")
    opts = []
    for v in range(int(q["scale_min"]), int(q["scale_max"]) + 1):
        checked = "checked" if saved is not None and str(saved) == str(v) else ""
        if isinstance(labels, list) and len(labels) == (int(q["scale_max"]) - int(q["scale_min"]) + 1):
            lab = labels[v - int(q["scale_min"])]
            opts.append(
                f"<label style='display:block; margin:6px 0;'>"
                f"<input type='radio' name='q:{q['key']}:{item['id']}' value='{v}' {checked}/> "
                f"{v}. {lab}</label>"
            )
        else:
            opts.append(
                f"<label style='display:inline-block; margin:6px 12px 6px 0;'>"
                f"<input type='radio' name='q:{q['key']}:{item['id']}' value='{v}' {checked}/> {v}</label>"
            )
    return "".join(opts)


@app.get("/questionnaires", response_class=HTMLResponse)
def questionnaires_home(request: Request, user: str = Depends(get_current_user)):
    state = _get_user_state(user)
    qs = _load_questionnaires()
    filled = state.get("questionnaires") or {}
    complete = _questionnaires_complete(state)
    rows = ["<h1>量表填写</h1>"]
    rows.append("<div class='card'><p>每个量表单独填写并保存。可随时返回继续。</p></div>")
    rows.append("<div class='card'><ul>")
    for q in qs:
        ans = filled.get(q["key"]) or {}
        total = len(q.get("items") or [])
        answered = len(ans) if isinstance(ans, dict) else 0
        status = "✅" if answered >= total and total > 0 else "⬜"
        rows.append(
            f"<li>{status} <a href='/questionnaires/{q['key']}'>{q['title']}</a> "
            f"<span class='muted'>({answered}/{total})</span></li>"
        )
    rows.append("</ul></div>")
    if complete:
        rows.append(
            "<div class='card'><b>量表已完成。</b> "
            "<a href='/annotate'>进入数据标注</a></div>"
        )
    else:
        rows.append(
            "<div class='card muted'>提示：量表全部完成后，系统会开放数据标注入口。</div>"
        )
    rows.append("<p><a href='/logout'>退出登录</a></p>")
    return _html_page("Questionnaires", "\n".join(rows))


@app.get("/questionnaires/{qkey}", response_class=HTMLResponse)
def questionnaires_one(qkey: str, request: Request, user: str = Depends(get_current_user)):
    state = _get_user_state(user)
    qs = {q["key"]: q for q in _load_questionnaires()}
    q = qs.get(qkey)
    if not q:
        raise HTTPException(status_code=404)
    saved = (state.get("questionnaires") or {}).get(q["key"], {})

    parts = [f"<h1>{q['title']}</h1>"]
    if q.get("instructions"):
        parts.append(f"<div class='card'><pre style='white-space:pre-wrap'>{q['instructions']}</pre></div>")
    parts.append(f"<form method='post' action='/questionnaires/{q['key']}'>")
    parts.append("<div class='card'>")
    for item in q.get("items") or []:
        item_id = item["id"]
        text = item.get("text", "")
        parts.append(f"<div style='margin-bottom:16px;'><div><b>{item_id}.</b> {text}</div>")
        parts.append(_render_item_options(q, item, saved.get(str(item_id))))
        parts.append("</div>")
    parts.append("</div>")
    parts.append("<button type='submit' name='action' value='save'>保存</button> ")
    parts.append("<button type='submit' name='action' value='save_back'>保存并返回</button>")
    parts.append("</form>")
    parts.append("<p><a href='/questionnaires'>返回量表列表</a></p>")
    return _html_page("Questionnaire", "\n".join(parts))


@app.post("/questionnaires/{qkey}")
async def questionnaires_one_submit(
    qkey: str,
    request: Request,
    action: str = Form("save"),
    user: str = Depends(get_current_user),
):
    state = _get_user_state(user)
    qs = {q["key"]: q for q in _load_questionnaires()}
    q = qs.get(qkey)
    if not q:
        raise HTTPException(status_code=404)
    form = await request.form()
    answers: Dict[str, Any] = {}
    for item in q.get("items") or []:
        k = f"q:{q['key']}:{item['id']}"
        if k in form:
            answers[str(item["id"])] = form[k]
    state.setdefault("questionnaires", {})
    state["questionnaires"][q["key"]] = answers
    _save_user_state(user, state)
    # If user completed all questionnaires, take them to annotation directly.
    if _questionnaires_complete(state) and action == "save_back":
        return RedirectResponse("/annotate", status_code=302)
    if action == "save_back":
        return RedirectResponse("/questionnaires", status_code=302)
    return RedirectResponse(f"/questionnaires/{q['key']}", status_code=302)


@app.get("/annotate", response_class=HTMLResponse)
def annotate_page(request: Request, user: str = Depends(get_current_user)):
    state = _get_user_state(user)
    records = _load_extractions()
    total = len(records)
    idx = min(state.get("progress_index", 0), max(total - 1, 0))
    record = records[idx] if records else None
    if not record:
        return _html_page("Annotate", "<p>没有可标注的记录。</p>")
    post = record.get("input", {})
    result = record.get("result", {}).get("extraction", {})
    post_id = record.get("meta", {}).get("post_id")
    media = record.get("result", {}).get("media_used", {})
    images = media.get("images", [])
    videos = media.get("videos", [])
    image_tags = "".join([f"<img src='/media?path={p}'/>" for p in images])
    video_tags = "".join([f"<video src='/media?path={p}' controls></video>" for p in videos])

    saved = (state.get("annotations") or {}).get(post_id) or {}
    initial_payload = saved.get("payload")
    if isinstance(initial_payload, str):
        try:
            initial_payload = json.loads(initial_payload)
        except json.JSONDecodeError:
            initial_payload = None
    initial = initial_payload if isinstance(initial_payload, dict) else result
    # Backward compatibility for older extractions.
    if isinstance(initial, dict):
        st = initial.get("stance")
        if isinstance(st, list):
            targets = []
            reasoning = []
            for it in st:
                if not isinstance(it, dict):
                    continue
                targets.append(
                    {
                        "target": it.get("target", ""),
                        "position": it.get("position", "neutral"),
                        "evidence": it.get("evidence") or [],
                        "confidence": it.get("confidence", 0),
                    }
                )
                reasoning.append(
                    {
                        "target": it.get("target", ""),
                        "opinion": it.get("reason", "") or it.get("opinion", ""),
                        "intent": it.get("intent", ""),
                        "evidence": it.get("evidence") or [],
                        "confidence": it.get("confidence", 0),
                    }
                )
            initial["stance"] = {"targets": targets, "reasoning": reasoning}
    initial_json = json.dumps(initial, ensure_ascii=False)
    return _html_page(
        "Annotate",
        f"""
<h1>微博标注 {idx+1}/{total}</h1>
<div class="card row">
  <div><b>Post ID:</b> {post_id}</div>
  <div class="muted">进度会按账号保存</div>
  <div style="margin-left:auto;"><a href="/logout">退出登录</a></div>
</div>
<div class="card"><pre>{post.get('content','')}</pre></div>
<div class="card media">{image_tags}{video_tags}</div>
<form method="post" action="/annotate">
  <div class="card">
    <label><input type="checkbox" name="correct" value="yes"/> 抽取结果整体正确（仅小改动）</label>
    <div class="muted" style="margin-top:8px;">
      标注提示：<span class="pill">topic=发帖原因/触发事件</span>
      <span class="pill">knowledge_facts=长期记忆/实体/经历</span>
      <span class="pill">tone=说话风格</span>
      <span class="pill">emotion=8大情绪</span>
    </div>
  </div>
  <div class="card">
    <h2>结构化标注</h2>
    <div class="muted">按字段逐项确认；可新增/删除条目；证据尽量使用原文的最小片段（多条用换行）。</div>
    <div id="ui"></div>
    <input type="hidden" name="payload_json" id="payload_json" />
  </div>
  <button type="submit" name="action" value="save">保存</button>
  <button type="submit" name="action" value="next">保存并下一条</button>
</form>
<details class="card"><summary>预览（只读）JSON</summary><pre id="preview"></pre></details>
<script id="initial" type="application/json">{initial_json}</script>
<script>
const initial = JSON.parse(document.getElementById("initial").textContent);
const ui = document.getElementById("ui");
const preview = document.getElementById("preview");
const payload = document.getElementById("payload_json");

function el(tag, attrs) {{
  const e = document.createElement(tag);
  if (attrs) for (const [k,v] of Object.entries(attrs)) {{
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else e.setAttribute(k, v);
  }}
  return e;
}}

function listEditor(title, hint, arr, placeholder) {{
  const box = el("div", {{class:"card"}});
  box.appendChild(el("h3", {{html:title}}));
  if (hint) box.appendChild(el("div", {{class:"muted", html:hint}}));
  const list = el("div");
  const add = (v="") => {{
    const row = el("div", {{class:"row", style:"margin:6px 0;"}} );
    const input = el("input", {{type:"text", value:v, placeholder:placeholder||"", style:"flex:1; padding:6px;"}});
    const del = el("button", {{type:"button"}});
    del.textContent = "删除";
    del.onclick = () => row.remove();
    row.appendChild(input);
    row.appendChild(del);
    list.appendChild(row);
  }};
  (arr||[]).forEach(v => add(v));
  const addBtn = el("button", {{type:"button"}});
  addBtn.textContent = "新增";
  addBtn.onclick = () => add("");
  box.appendChild(list);
  box.appendChild(addBtn);
  box._get = () => Array.from(list.querySelectorAll("input")).map(i => i.value.trim()).filter(Boolean);
  return box;
}}

function evidenceArea(label, value) {{
  const wrap = el("div", {{style:"margin-top:6px;"}});
  wrap.appendChild(el("div", {{class:"muted", html:label}}));
  const ta = el("textarea", {{style:"height:80px;", placeholder:"每行一条证据"}});
  ta.value = (value||[]).join("\\n");
  wrap.appendChild(ta);
  wrap._get = () => ta.value.split("\\n").map(s=>s.trim()).filter(Boolean);
  return wrap;
}}

function number01(label, value) {{
  const wrap = el("div", {{style:"margin-top:6px;"}});
  wrap.appendChild(el("div", {{class:"muted", html:label}}));
  const inp = el("input", {{type:"number", step:"0.01", min:"0", max:"1", value: (value ?? 0), style:"padding:6px; width:120px;"}});
  wrap.appendChild(inp);
  wrap._get = () => {{
    const v = parseFloat(inp.value);
    return Number.isFinite(v) ? v : 0;
  }};
  return wrap;
}}

function toneMulti(values) {{
  const options = ["formal","casual","celebratory","persuasive","objective","humorous","sarcastic","empathetic","authoritative","promotional","instructional","narrative","urgent","reflective"];
  const set = new Set(values||[]);
  const box = el("div", {{style:"margin-top:10px;"}} );
  options.forEach(o => {{
    const id = "tone_" + o;
    const cb = el("input", {{type:"checkbox", id}});
    cb.checked = set.has(o);
    cb.dataset.val = o;
    const lab = el("label", {{for:id, style:"margin-right:12px; display:inline-block;"}});
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(" "+o));
    box.appendChild(lab);
  }});
  box._get = () => Array.from(box.querySelectorAll("input[type=checkbox]")).filter(x=>x.checked).map(x=>x.dataset.val);
  return box;
}}

function selectOne(label, options, value) {{
  const wrap = el("div", {{style:"margin-top:10px;"}} );
  wrap.appendChild(el("div", {{class:"muted", html:label}}));
  const sel = el("select", {{style:"padding:6px; width:260px;"}} );
  options.forEach(o => {{
    const opt = el("option", {{value:o}});
    opt.textContent = o;
    if (o === value) opt.selected = true;
    sel.appendChild(opt);
  }});
  wrap.appendChild(sel);
  wrap._get = () => sel.value;
  return wrap;
}}

function objectListEditor(title, hint, items, fields) {{
  const box = el("div", {{class:"card"}});
  box.appendChild(el("h3", {{html:title}}));
  if (hint) box.appendChild(el("div", {{class:"muted", html:hint}}));
  const list = el("div");
  const add = (init={{}}) => {{
    const row = el("div", {{style:"border:1px solid #eee; padding:10px; margin:10px 0; border-radius:8px;"}});
    fields.forEach(f => {{
      row.appendChild(el("div", {{class:"muted", html:f.label}}));
      let input;
      if (Array.isArray(f.options)) {{
        input = el("select", {{style:"width:100%; padding:6px;"}});
        f.options.forEach(o => {{
          const opt = el("option", {{value:o}});
          opt.textContent = o;
          if (String(o) === String(init[f.key]||\"\")) opt.selected = true;
          input.appendChild(opt);
        }});
      }} else {{
        input = el("input", {{type:"text", value:(init[f.key]||\"\"), style:"width:100%; padding:6px;"}});
      }}
      input.dataset.key = f.key;
      row.appendChild(input);
    }});
    const del = el("button", {{type:"button", style:"margin-top:8px;"}} );
    del.textContent = "删除条目";
    del.onclick = () => row.remove();
    row.appendChild(del);
    list.appendChild(row);
  }};
  (items||[]).forEach(it => add(it));
  const addBtn = el("button", {{type:"button"}});
  addBtn.textContent = "新增";
  addBtn.onclick = () => add({{}});
  box.appendChild(list);
  box.appendChild(addBtn);
  box._rows = () => Array.from(list.children);
  return box;
}}

const style = initial.style || {{}};
const stance = initial.stance || {{}};
const topic = initial.topic || {{}};
const safety = initial.safety_rewrite || {{}};

const styleBox = el("div");
styleBox.appendChild(listEditor("catchphrases", "口头禅/常用短语；没有就留空", style.catchphrases, "短语"));
styleBox.appendChild(listEditor("signature_patterns", "标志性句式/结构；没有就留空", style.signature_patterns, "句式"));
const toneBox = el("div", {{class:"card"}});
toneBox.appendChild(el("h3", {{html:"tone"}}));
toneBox.appendChild(el("div", {{class:"muted", html:"说话风格/语气，可多选 1-3 个"}}));
const toneCtl = toneMulti(style.tone);
toneBox.appendChild(toneCtl);
const emoCtl = selectOne("emotion（8大情绪；无明显则 none）", ["none","joy","trust","fear","surprise","sadness","disgust","anger","anticipation"], style.emotion || "none");
toneBox.appendChild(emoCtl);
const stEv = evidenceArea("style.evidence", style.evidence);
const stCf = number01("style.confidence (0-1)", style.confidence);
toneBox.appendChild(stEv);
toneBox.appendChild(stCf);
styleBox.appendChild(toneBox);

const safetyBox = el("div");
const terms = objectListEditor("safety_rewrite.terms", "敏感/需替换表述；没有就留空", safety.terms, [
  {{key:"term", label:"term（原词/原表述）"}},
  {{key:"replacement", label:"replacement（替换表述）"}},
]);
const sEv = evidenceArea("safety_rewrite.evidence", safety.evidence);
const sCf = number01("safety_rewrite.confidence (0-1)", safety.confidence);
terms.appendChild(sEv);
terms.appendChild(sCf);
safetyBox.appendChild(terms);

const stanceBox = el("div");
const stTargets = objectListEditor("stance.targets", "目标对象 + 立场（support/oppose/neutral）。证据多条用换行。", stance.targets, [
  {{key:"target", label:"target"}},
  {{key:"position", label:"position", options:["support","oppose","neutral"]}},
  {{key:"evidence", label:"evidence（用 \\n 分隔）"}},
  {{key:"confidence", label:"confidence(0-1)"}},
]);
const stReason = objectListEditor("stance.reasoning", "观点 + 意图。证据多条用换行。", stance.reasoning, [
  {{key:"target", label:"target"}},
  {{key:"opinion", label:"opinion"}},
  {{key:"intent", label:"intent"}},
  {{key:"evidence", label:"evidence（用 \\n 分隔）"}},
  {{key:"confidence", label:"confidence(0-1)"}},
]);
stanceBox.appendChild(stTargets);
stanceBox.appendChild(stReason);

const topicBox = el("div", {{class:"card"}});
topicBox.appendChild(el("h3", {{html:"topic"}}));
topicBox.appendChild(el("div", {{class:"muted", html:"topic 是“因为什么而发帖”的一句话动机描述；不要写成泛化主题词"}}));
const trig = el("input", {{type:"text", value:(topic.trigger||""), style:"width:100%; padding:6px;", placeholder:"触发事件/原因关键词"}} );
const summ = el("input", {{type:"text", value:(topic.one_sentence_summary||\"\"), style:\"width:100%; padding:6px; margin-top:8px;\", placeholder:\"一句话：因为什么而发帖\"}} );
topicBox.appendChild(trig);
topicBox.appendChild(summ);
const tpEv = evidenceArea("topic.evidence", topic.evidence);
const tpCf = number01("topic.confidence (0-1)", topic.confidence);
topicBox.appendChild(tpEv);
topicBox.appendChild(tpCf);

const kbBox = objectListEditor("knowledge_facts", "长期实体/经历/价值取向；不要写一次性事件（如“第500万辆下线”）", initial.knowledge_facts, [
  {{key:"fact", label:"fact"}},
  {{key:"evidence", label:"evidence（用 \\n 分隔）"}},
  {{key:"confidence", label:"confidence(0-1)"}},
]);

ui.appendChild(el("div", {{class:"card", html:"<h2>style</h2><div class='muted'>用于角色“写作风格/语气”。没有就留空。</div>"}}));
ui.appendChild(styleBox);
ui.appendChild(el("div", {{class:"card", html:"<h2>stance</h2><div class='muted'>用于角色“立场/观点/意图”。目标对象可以是具体品牌/个人/组织，也可以是宏观对象（行业/市场）。</div>"}}));
ui.appendChild(stanceBox);
ui.appendChild(el("div", {{class:"card", html:"<h2>topic</h2><div class='muted'>用于驱动虚拟角色发帖：写清楚“因为什么发帖”。</div>"}}));
ui.appendChild(topicBox);
ui.appendChild(el("div", {{class:"card", html:"<h2>knowledge_facts</h2><div class='muted'>用于构建角色记忆库：稳定实体、长期偏好、经历、价值取向线索。</div>"}}));
ui.appendChild(kbBox);
ui.appendChild(el("div", {{class:"card", html:"<h2>safety_rewrite</h2><div class='muted'>不是审查，是替换表述表（若无则空）。</div>"}}));
ui.appendChild(safetyBox);

function rowsToObjects(box, requiredKeys) {{
  const out = [];
  box._rows().forEach(row => {{
    const obj = {{}};
    row.querySelectorAll(\"input[data-key]\").forEach(i => obj[i.dataset.key] = (i.value||\"\").trim());
    if (obj.evidence) obj.evidence = obj.evidence.split(\"\\n\").map(s=>s.trim()).filter(Boolean);
    if (obj.confidence !== undefined) {{
      const c = parseFloat(obj.confidence);
      obj.confidence = Number.isFinite(c) ? c : 0;
    }}
    if (requiredKeys.some(k => obj[k])) out.push(obj);
  }});
  return out;
}}

function buildPayload() {{
  const obj = {{
    post_id: initial.post_id || "{post_id}",
    style: {{
      catchphrases: styleBox.querySelectorAll(\".card\")[0]._get(),
      signature_patterns: styleBox.querySelectorAll(\".card\")[1]._get(),
      tone: toneCtl._get(),
      emotion: emoCtl._get(),
      evidence: stEv._get(),
      confidence: stCf._get(),
    }},
    safety_rewrite: {{
      terms: rowsToObjects(terms, [\"term\",\"replacement\"]).map(o => ({{term:o.term||\"\", replacement:o.replacement||\"\"}})),
      evidence: sEv._get(),
      confidence: sCf._get(),
    }},
    stance: {{
      targets: rowsToObjects(stTargets, [\"target\"]).map(o => ({{target:o.target||\"\", position:o.position||\"neutral\", evidence:o.evidence||[], confidence:o.confidence||0}})),
      reasoning: rowsToObjects(stReason, [\"target\"]).map(o => ({{target:o.target||\"\", opinion:o.opinion||\"\", intent:o.intent||\"\", evidence:o.evidence||[], confidence:o.confidence||0}})),
    }},
    topic: {{
      trigger: (trig.value||\"\").trim(),
      one_sentence_summary: (summ.value||\"\").trim(),
      evidence: tpEv._get(),
      confidence: tpCf._get(),
    }},
    knowledge_facts: rowsToObjects(kbBox, [\"fact\"]).map(o => ({{fact:o.fact||\"\", evidence:o.evidence||[], confidence:o.confidence||0}})),
  }};
  payload.value = JSON.stringify(obj);
  preview.textContent = JSON.stringify(obj, null, 2);
}}

buildPayload();
document.querySelector(\"form\").addEventListener(\"submit\", buildPayload);
</script>
""",
    )


@app.post("/annotate")
async def annotate_submit(
    request: Request,
    action: str = Form("save"),
    payload_json: str = Form(""),
    correct: Optional[str] = Form(None),
    user: str = Depends(get_current_user),
):
    state = _get_user_state(user)
    records = _load_extractions()
    total = len(records)
    idx = min(state.get("progress_index", 0), max(total - 1, 0))
    record = records[idx] if records else None
    if record:
        post_id = record.get("meta", {}).get("post_id")
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        state["annotations"][post_id] = {
            "correct": bool(correct),
            "payload": payload,
            "updated_at": time.time(),
        }
    if action == "next":
        state["progress_index"] = min(idx + 1, max(total - 1, 0))
    _save_user_state(user, state)
    return RedirectResponse("/annotate", status_code=302)


@app.get("/media")
def serve_media(path: str, user: str = Depends(get_current_user)):
    resolved = Path(path).resolve()
    if not str(resolved).startswith(str(WEIBO_ROOT)):
        raise HTTPException(status_code=403)
    if not resolved.exists():
        raise HTTPException(status_code=404)
    return FileResponse(resolved)
