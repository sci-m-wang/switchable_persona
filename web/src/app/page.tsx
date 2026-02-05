'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { AnnotationEntry, NormalizedTask, UserState } from '@/lib/types';
import { clearState, downloadJson, loadState, saveState } from '@/lib/storage';
import { normalizeTasks, parseJsonOrJsonl } from '@/lib/parse';

type QuestionnaireDef = {
  key: string;
  title: string;
  instructions?: string;
  scaleMin: number;
  scaleMax: number;
  items: { id: string; text: string; options?: Record<string, any>; labels?: string[] }[];
};

function nowTs() {
  return Date.now();
}

function defaultState(): UserState {
  return {
    annotatorId: '',
    consent: { agreed: false, signedName: '' },
    questionnaires: {},
    progressIndex: 0,
    annotations: {}
  };
}

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

async function loadQuestionnaires(): Promise<QuestionnaireDef[]> {
  const names = ['16Personalities.json', 'BFI.json', 'PVQ.json', 'EIS.json', 'LMS.json'];
  const defs: QuestionnaireDef[] = [];

  for (const name of names) {
    const res = await fetch(`/questionnaires/${name}`, { cache: 'no-store' });
    if (!res.ok) continue;
    const raw = await res.json();

    const key = String(raw.name || raw.id || raw.title || raw.full_name || name.replace(/\.json$/i, ''));
    const title = String(raw.full_name || raw.title || raw.name || key);
    const instructions = String(
      raw.psychobench_prompt_choice_instruction || raw.instructions || raw.psychobench_prompt || ''
    );

    let scaleMin = 1;
    let scaleMax = 7;
    if (Array.isArray(raw.range) && raw.range.length === 2) {
      scaleMin = Number(raw.range[0]);
      scaleMax = Number(raw.range[1]);
    } else if (raw.response_scale && typeof raw.response_scale === 'object') {
      scaleMin = Number(raw.response_scale.min ?? 1);
      scaleMax = Number(raw.response_scale.max ?? 7);
    }

    let labels: string[] | undefined;
    if (raw.response_scale && typeof raw.response_scale === 'object' && Array.isArray(raw.response_scale.labels)) {
      labels = raw.response_scale.labels.map((x: any) => String(x));
    }

    const items: QuestionnaireDef['items'] = [];
    if (raw.questions && typeof raw.questions === 'object') {
      for (const [qid, qitem] of Object.entries(raw.questions)) {
        const it = qitem as any;
        const text = String(it.rewritten_zh || it.origin_zh || it.origin_en || '');
        const out: any = { id: String(qid), text };
        if (it.options && typeof it.options === 'object') out.options = it.options;
        if (labels) out.labels = labels;
        items.push(out);
      }
    } else if (Array.isArray(raw.items)) {
      for (const it of raw.items) {
        const qid = (it as any).id || (it as any).qid || (it as any).key;
        const text = String((it as any).text || (it as any).origin_zh || (it as any).origin_en || '');
        const out: any = { id: String(qid), text };
        if (labels) out.labels = labels;
        items.push(out);
      }
    }

    defs.push({ key, title, instructions, scaleMin, scaleMax, items });
  }

  return defs;
}

function isQuestionnairesComplete(state: UserState, defs: QuestionnaireDef[]) {
  for (const q of defs) {
    const filled = state.questionnaires[q.key] || {};
    if (Object.keys(filled).length < q.items.length) return false;
  }
  return defs.length > 0;
}

export default function Page() {
  const [tasks, setTasks] = useState<NormalizedTask[]>([]);
  const [state, setState] = useState<UserState>(defaultState);
  const [datasetUrl, setDatasetUrl] = useState('');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [payloadText, setPayloadText] = useState('');
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const [questionnaires, setQuestionnaires] = useState<QuestionnaireDef[]>([]);
  const [qLoading, setQLoading] = useState(false);

  const saveTimer = useRef<number | null>(null);

  useEffect(() => {
    const st = loadState();
    if (st) setState(st);
  }, []);

  useEffect(() => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => saveState(state), 250);
  }, [state]);

  const readyToAnnotate = useMemo(() => {
    if (!state.annotatorId.trim()) return false;
    if (!state.consent.agreed) return false;
    if (questionnaires.length === 0) return false;
    if (!isQuestionnairesComplete(state, questionnaires)) return false;
    if (tasks.length === 0) return false;
    return true;
  }, [state, questionnaires, tasks]);

  const total = tasks.length;
  const idx = clamp(state.progressIndex || 0, 0, Math.max(0, total - 1));
  const current = tasks[idx];

  // Keep payloadText in sync with current task + saved annotations.
  useEffect(() => {
    if (!current) {
      setPayloadText('');
      setPayloadError(null);
      return;
    }

    const saved = state.annotations[current.postId];
    const initial = saved?.payload ?? current.extraction ?? {};
    setPayloadText(JSON.stringify(initial, null, 2));
    setPayloadError(null);
  }, [current?.postId]);

  async function onLoadFromUrl() {
    setLoadError(null);
    try {
      const res = await fetch(datasetUrl, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      const parsed = parseJsonOrJsonl(text);
      const normalized = normalizeTasks(parsed);
      if (normalized.length === 0) throw new Error('No usable records (missing post_id/content).');
      setTasks(normalized);
      setState((s) => ({
        ...s,
        progressIndex: 0,
        datasetInfo: { source: datasetUrl, loadedAt: nowTs(), total: normalized.length }
      }));
    } catch (e: any) {
      setLoadError(String(e?.message || e));
    }
  }

  async function onLoadFromFile(file: File) {
    setLoadError(null);
    try {
      const text = await file.text();
      const parsed = parseJsonOrJsonl(text);
      const normalized = normalizeTasks(parsed);
      if (normalized.length === 0) throw new Error('No usable records (missing post_id/content).');
      setTasks(normalized);
      setState((s) => ({
        ...s,
        progressIndex: 0,
        datasetInfo: { source: `file:${file.name}`, loadedAt: nowTs(), total: normalized.length }
      }));
    } catch (e: any) {
      setLoadError(String(e?.message || e));
    }
  }

  async function ensureQuestionnairesLoaded() {
    if (questionnaires.length > 0) return;
    setQLoading(true);
    try {
      const defs = await loadQuestionnaires();
      setQuestionnaires(defs);
    } finally {
      setQLoading(false);
    }
  }

  function setAnswer(qKey: string, itemId: string, value: string) {
    setState((s) => ({
      ...s,
      questionnaires: {
        ...s.questionnaires,
        [qKey]: {
          ...(s.questionnaires[qKey] || {}),
          [itemId]: value
        }
      }
    }));
  }

  function parsePayloadOrSetError(): unknown | null {
    try {
      const obj = JSON.parse(payloadText || '{}');
      setPayloadError(null);
      return obj;
    } catch (e: any) {
      setPayloadError(String(e?.message || e));
      return null;
    }
  }

  function saveCurrent(next: boolean) {
    if (!current) return;
    const payload = parsePayloadOrSetError();
    if (payload === null) return;

    const entry: AnnotationEntry = {
      correct: state.annotations[current.postId]?.correct ?? false,
      payload,
      updatedAt: nowTs()
    };

    setState((s) => {
      const nextIndex = next ? clamp(idx + 1, 0, Math.max(0, total - 1)) : idx;
      return {
        ...s,
        progressIndex: nextIndex,
        annotations: { ...s.annotations, [current.postId]: entry }
      };
    });
  }

  function resetPayload() {
    if (!current) return;
    setPayloadText(JSON.stringify(current.extraction ?? {}, null, 2));
    setPayloadError(null);
  }

  function exportAll() {
    const safeId = state.annotatorId.trim() || 'unknown';
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    downloadJson(`annotations_${safeId}_${ts}.json`, {
      ...state,
      exportAt: nowTs(),
      tasksTotal: total
    });
  }

  function importState(file: File) {
    file.text().then((text) => {
      const obj = JSON.parse(text) as UserState;
      setState(obj);
    });
  }

  return (
    <div className="row" style={{ alignItems: 'stretch' }}>
      <div style={{ flex: 1, minWidth: 320 }}>
        <h1>标注工具（Vercel 友好版）</h1>
        <div className="muted">
          纯浏览器保存（localStorage）+ 导出 JSON。适合 Vercel 免费版静态部署。
        </div>

        <div style={{ height: 12 }} />

        <div className="card">
          <h2>1) 标注者信息</h2>
          <div className="grid2">
            <div>
              <div className="muted">Annotator ID（用于区分导出文件）</div>
              <input
                type="text"
                value={state.annotatorId}
                onChange={(e) => setState((s) => ({ ...s, annotatorId: e.target.value }))}
                placeholder="e.g. annotator1"
              />
            </div>
            <div>
              <div className="muted">导入旧标注（可跨设备迁移）</div>
              <input
                type="file"
                accept="application/json"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) importState(f);
                }}
              />
            </div>
          </div>
          <div style={{ height: 10 }} />
          <div className="row">
            <label className="badge">
              <input
                type="checkbox"
                checked={state.consent.agreed}
                onChange={(e) =>
                  setState((s) => ({
                    ...s,
                    consent: {
                      ...s.consent,
                      agreed: e.target.checked,
                      signedAt: e.target.checked ? nowTs() : undefined
                    }
                  }))
                }
              />
              我同意协议（本地保存）
            </label>
            <div style={{ flex: 1 }} />
            <button
              className="danger"
              onClick={() => {
                clearState();
                setState(defaultState());
                setTasks([]);
                setPayloadText('');
                setPayloadError(null);
              }}
            >
              清空本地状态
            </button>
          </div>
          <div style={{ height: 10 }} />
          <div className="muted">签名（姓名/昵称，可选）</div>
          <input
            type="text"
            value={state.consent.signedName}
            onChange={(e) => setState((s) => ({ ...s, consent: { ...s.consent, signedName: e.target.value } }))}
            placeholder="可选"
          />
        </div>

        <div style={{ height: 12 }} />

        <div className="card">
          <h2>2) 加载任务数据</h2>
          <div className="muted">支持 JSON 数组 / JSONL（每行一个 JSON）。要求至少包含 post_id 与 content。</div>
          <div style={{ height: 10 }} />
          <div className="grid2">
            <div>
              <div className="muted">从 URL 加载（建议用 GitHub Release 资产直链 / 云盘直链）</div>
              <input
                type="url"
                value={datasetUrl}
                onChange={(e) => setDatasetUrl(e.target.value)}
                placeholder="https://.../extractions.jsonl"
              />
              <div style={{ height: 10 }} />
              <button className="primary" onClick={onLoadFromUrl} disabled={!datasetUrl.trim()}>
                从 URL 加载
              </button>
            </div>
            <div>
              <div className="muted">从本地文件加载</div>
              <input
                type="file"
                accept="application/json,.jsonl,.txt"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onLoadFromFile(f);
                }}
              />
              <div style={{ height: 10 }} />
              <div className="badge">已加载：{tasks.length} 条</div>
              {state.datasetInfo?.source ? <div className="muted">来源：{state.datasetInfo.source}</div> : null}
            </div>
          </div>
          {loadError ? <div className="error" style={{ marginTop: 10 }}>加载失败：{loadError}</div> : null}
        </div>

        <div style={{ height: 12 }} />

        <div className="card">
          <h2>3) 量表（本地填写）</h2>
          <div className="row">
            <button className="primary" onClick={ensureQuestionnairesLoaded} disabled={qLoading}>
              {qLoading ? '加载中…' : '加载量表'}
            </button>
            <div className="muted">构建时会从仓库根目录 questionnaires/ 复制 5 个量表到 public/</div>
          </div>

          {questionnaires.length === 0 ? null : (
            <>
              <hr />
              {questionnaires.map((q) => {
                const filled = state.questionnaires[q.key] || {};
                return (
                  <div key={q.key} className="card" style={{ marginTop: 10 }}>
                    <div className="row">
                      <div style={{ fontWeight: 700 }}>{q.title}</div>
                      <div className="badge">{Object.keys(filled).length}/{q.items.length}</div>
                    </div>
                    {q.instructions ? <pre style={{ whiteSpace: 'pre-wrap' }} className="muted">{q.instructions}</pre> : null}

                    {q.items.slice(0, 12).map((it) => {
                      const saved = filled[it.id];
                      const opts: { val: string; label: string }[] = [];

                      if (it.options && typeof it.options === 'object') {
                        for (const [val, meta] of Object.entries(it.options)) {
                          const m = meta as any;
                          opts.push({ val: String(val), label: String(m?.zh || m?.en || val) });
                        }
                      } else {
                        for (let v = q.scaleMin; v <= q.scaleMax; v++) {
                          const lab = it.labels && it.labels.length === q.scaleMax - q.scaleMin + 1 ? it.labels[v - q.scaleMin] : String(v);
                          opts.push({ val: String(v), label: lab });
                        }
                      }

                      return (
                        <div key={it.id} style={{ marginTop: 10 }}>
                          <div style={{ fontWeight: 600 }}>{it.id}. {it.text}</div>
                          <div className="row" style={{ marginTop: 8 }}>
                            {opts.map((o) => (
                              <label key={o.val} className="badge" style={{ cursor: 'pointer' }}>
                                <input
                                  type="radio"
                                  name={`q:${q.key}:${it.id}`}
                                  checked={saved === o.val}
                                  onChange={() => setAnswer(q.key, it.id, o.val)}
                                />
                                {o.val}. {o.label}
                              </label>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                    {q.items.length > 12 ? <div className="muted" style={{ marginTop: 8 }}>为避免页面过长，这里只展示前 12 题；如需全部题目我可以把渲染改为分页。</div> : null}
                  </div>
                );
              })}
              <div style={{ marginTop: 10 }} className={isQuestionnairesComplete(state, questionnaires) ? 'ok' : 'error'}>
                {isQuestionnairesComplete(state, questionnaires) ? '量表：已完成' : '量表：未完成（每个量表需全部作答）'}
              </div>
            </>
          )}
        </div>

        <div style={{ height: 12 }} />

        <div className="card">
          <h2>4) 导出</h2>
          <div className="row">
            <button className="primary" onClick={exportAll} disabled={!state.annotatorId.trim()}>
              导出标注 JSON
            </button>
            <div className="muted">建议每次标注 20-50 条就导出一次备份。</div>
          </div>
        </div>
      </div>

      <div style={{ width: 520, minWidth: 360, flexShrink: 0 }}>
        <div className="card">
          <h2>标注区</h2>
          <div className="row">
            <div className="badge">进度：{total === 0 ? '0/0' : `${idx + 1}/${total}`}</div>
            <div className="badge">状态：{readyToAnnotate ? '可标注' : '未就绪'}</div>
            <div style={{ flex: 1 }} />
            <button onClick={() => setState((s) => ({ ...s, progressIndex: clamp((s.progressIndex || 0) - 1, 0, Math.max(0, total - 1)) }))}>
              上一条
            </button>
            <button onClick={() => setState((s) => ({ ...s, progressIndex: clamp((s.progressIndex || 0) + 1, 0, Math.max(0, total - 1)) }))}>
              下一条
            </button>
          </div>

          <div style={{ height: 12 }} />

          {!readyToAnnotate ? (
            <div className="muted">
              需要满足：Annotator ID、同意协议、量表完成、已加载数据。
            </div>
          ) : null}

          <div style={{ height: 12 }} />

          {current ? (
            <>
              <div className="muted">Post ID</div>
              <div style={{ fontWeight: 700, wordBreak: 'break-all' }}>{current.postId}</div>

              <div style={{ height: 10 }} />
              <div className="muted">内容</div>
              <pre className="card" style={{ whiteSpace: 'pre-wrap' }}>{current.content || '(empty)'}</pre>

              {(current.media.images?.length || current.media.videos?.length) ? (
                <>
                  <div className="muted">媒体（仅展示 http(s) 链接；本地路径不会上传到 Vercel）</div>
                  <div className="row">
                    {(current.media.images || []).map((u) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={u} src={u} alt="image" style={{ maxWidth: 160, borderRadius: 12, border: '1px solid var(--border)' }} />
                    ))}
                    {(current.media.videos || []).map((u) => (
                      <video key={u} src={u} controls style={{ maxWidth: 240, borderRadius: 12, border: '1px solid var(--border)' }} />
                    ))}
                  </div>
                </>
              ) : null}

              <div style={{ height: 10 }} />

              <label className="badge" style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={Boolean(state.annotations[current.postId]?.correct)}
                  onChange={(e) => {
                    setState((s) => ({
                      ...s,
                      annotations: {
                        ...s.annotations,
                        [current.postId]: {
                          payload: s.annotations[current.postId]?.payload ?? current.extraction ?? {},
                          updatedAt: nowTs(),
                          correct: e.target.checked
                        }
                      }
                    }));
                  }}
                />
                抽取结果整体正确（仅小改动）
              </label>

              <div style={{ height: 10 }} />

              <div className="row">
                <button onClick={resetPayload}>重置为抽取结果</button>
                <button className="primary" onClick={() => saveCurrent(false)} disabled={!readyToAnnotate}>
                  保存
                </button>
                <button className="primary" onClick={() => saveCurrent(true)} disabled={!readyToAnnotate}>
                  保存并下一条
                </button>
              </div>

              <div style={{ height: 10 }} />
              <div className="muted">payload（JSON，可直接编辑）</div>
              <textarea value={payloadText} onChange={(e) => setPayloadText(e.target.value)} />
              {payloadError ? <div className="error">JSON 解析错误：{payloadError}</div> : null}

              <div style={{ height: 10 }} />
              <button
                onClick={() => {
                  const p = parsePayloadOrSetError();
                  if (p !== null) alert('JSON 合法');
                }}
              >
                校验 JSON
              </button>
            </>
          ) : (
            <div className="muted">尚未加载任务数据。</div>
          )}
        </div>
      </div>
    </div>
  );
}
