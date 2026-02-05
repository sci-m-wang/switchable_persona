import type { ExtractionRecord, NormalizedTask } from '@/lib/types';

export function parseJsonOrJsonl(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return [];

  // If it looks like JSON array/object, parse directly.
  if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
    return JSON.parse(trimmed);
  }

  // Otherwise treat as JSONL.
  const lines = trimmed.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.map((l) => JSON.parse(l));
}

export function normalizeTasks(raw: unknown): NormalizedTask[] {
  const arr = Array.isArray(raw) ? raw : [raw];
  const tasks: NormalizedTask[] = [];

  for (const item of arr) {
    if (!item || typeof item !== 'object') continue;

    // Accept either original extraction record shape or a simplified task shape.
    const rec = item as ExtractionRecord & {
      post_id?: string;
      content?: string;
      extraction?: unknown;
      images?: string[];
      videos?: string[];
    };

    const postId =
      rec.meta?.post_id ||
      rec.post_id ||
      // Some pipelines may use id
      (rec as any).id ||
      '';

    const content = rec.input?.content || rec.content || '';

    const sourceUrl =
      (typeof rec.input?.article_url === 'string' ? rec.input?.article_url : '') ||
      (typeof rec.input?.articleUrl === 'string' ? rec.input?.articleUrl : '') ||
      (typeof (rec as any).article_url === 'string' ? (rec as any).article_url : '') ||
      (typeof (rec as any).articleUrl === 'string' ? (rec as any).articleUrl : '') ||
      undefined;

    const extraction = rec.result?.extraction ?? rec.extraction ?? {};

    const images = (rec.result?.media_used?.images ?? rec.images ?? []).filter((p) => typeof p === 'string');

    const videos = (rec.result?.media_used?.videos ?? rec.videos ?? []).filter((p) => typeof p === 'string');

    if (!postId) continue;

    tasks.push({
      postId,
      content,
      sourceUrl,
      extraction,
      media: { images, videos }
    });
  }

  return tasks;
}
