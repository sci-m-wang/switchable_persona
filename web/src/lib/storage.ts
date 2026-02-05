import type { UserState } from '@/lib/types';

const KEY = 'switchable_persona_annotation_state_v1';

export function loadState(): UserState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as UserState;
  } catch {
    return null;
  }
}

export function saveState(state: UserState): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(KEY, JSON.stringify(state));
}

export function clearState(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(KEY);
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
