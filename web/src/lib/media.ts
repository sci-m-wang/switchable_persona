export function isHttpUrl(s: string): boolean {
  return /^https?:\/\//i.test(s);
}

function stripLeadingSlashes(s: string): string {
  return s.replace(/^\/+/, '');
}

function joinUrl(base: string, path: string): string {
  const b = base.replace(/\/+$/, '');
  const p = stripLeadingSlashes(path);
  return `${b}/${p}`;
}

/**
 * Resolve a media path into a http(s) URL.
 *
 * Supported inputs:
 * - already-http(s) URLs: returned as is
 * - absolute local paths: /.../weibo/...  (strip prefix then join with base)
 * - relative weibo paths: weibo/... or ./weibo/... (strip leading ./ then join)
 */
export function resolveMediaUrl(
  mediaPath: string,
  cfg: { mediaBaseUrl?: string; localWeiboPrefix?: string }
): string | null {
  const raw = String(mediaPath || '').trim();
  if (!raw) return null;
  if (isHttpUrl(raw)) return raw;

  const base = (cfg.mediaBaseUrl || '').trim();
  if (!base) return null;

  let rel: string | null = null;

  const prefix = (cfg.localWeiboPrefix || '').trim();
  if (prefix && raw.startsWith(prefix)) {
    rel = raw.slice(prefix.length);
  }

  if (rel === null) {
    const normalized = raw.replace(/^\.\//, '');
    if (normalized.startsWith('weibo/')) {
      rel = normalized;
    }
  }

  if (rel === null) return null;
  rel = stripLeadingSlashes(rel);

  // If user provided base already ends with /weibo, and rel also starts with weibo/,
  // avoid duplicating.
  if (base.replace(/\/+$/, '').endsWith('/weibo') && rel.startsWith('weibo/')) {
    rel = rel.slice('weibo/'.length);
  }

  return joinUrl(base, rel);
}
