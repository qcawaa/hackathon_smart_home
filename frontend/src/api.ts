export const API = 'http://localhost:8000/api';
export async function request<T = any>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.error?.message || body?.detail?.error?.message || 'Не удалось выполнить запрос');
  return body as T;
}
export const wsUrl = 'ws://localhost:8000/ws/events';
