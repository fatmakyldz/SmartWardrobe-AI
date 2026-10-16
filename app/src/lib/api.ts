import { Platform } from 'react-native';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export type Category = 'top' | 'bottom' | 'dress' | 'outerwear' | 'shoes' | 'accessory' | 'bag';
export type Occasion = 'casual' | 'work' | 'formal' | 'date' | 'sport' | 'party' | 'travel';

export const CATEGORIES: Category[] = ['top', 'bottom', 'dress', 'outerwear', 'shoes', 'bag', 'accessory'];
export const OCCASIONS: Occasion[] = ['casual', 'work', 'date', 'formal', 'party', 'sport', 'travel'];
export const COLORS = [
  'black', 'white', 'grey', 'navy', 'blue', 'lightblue', 'green', 'olive', 'beige', 'cream', 'brown',
  'khaki', 'red', 'burgundy', 'pink', 'purple', 'yellow', 'orange', 'gold', 'silver', 'multi',
] as const;
export const PATTERNS = ['solid', 'striped', 'checked', 'floral', 'printed', 'denim', 'knit', 'leather', 'other'] as const;
export const SEASONS = ['spring', 'summer', 'autumn', 'winter'] as const;

// Swatch colours for the colour picker.
export const SWATCH: Record<string, string> = {
  black: '#1d1d1f', white: '#fbfbf8', grey: '#9b9da3', navy: '#273452', blue: '#4f6f99', lightblue: '#b9d0e8',
  green: '#3f7a4f', olive: '#7c8452', beige: '#d4be96', cream: '#efe3cb', brown: '#7a5235', khaki: '#a99a6b',
  red: '#c0392b', burgundy: '#7e2639', pink: '#e8a3b5', purple: '#6c4a8a', yellow: '#e9c84a', orange: '#df7a35',
  gold: '#c9a646', silver: '#c4c6ca', multi: 'conic',
};

export type User = {
  id: string;
  email: string;
  name: string;
  locale: 'en' | 'tr';
  city: string;
  lat: number | null;
  lon: number | null;
  is_demo: boolean;
};

export type Tags = {
  name: string;
  category: Category;
  subcategory: string;
  colors: string[];
  pattern: string;
  warmth: number;
  formality: number;
  seasons: string[];
};

export type Item = Tags & { id: string; image_url: string; created_at: string };

export type Weather = {
  temp: number | null;
  feels_like: number | null;
  wind_kmh: number | null;
  code: number | null;
  min: number | null;
  max: number | null;
  rain_chance: number | null;
};

export type Outfit = {
  id: string;
  title: string;
  reason: string;
  occasion: Occasion;
  note: string;
  weather: Partial<Weather>;
  rating: -1 | 0 | 1;
  items: Item[];
  created_at: string;
};

export type City = { name: string | null; label: string; lat: number; lon: number };

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code);
  }
}

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  token = t;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export function imageUrl(url: string): string {
  return url.startsWith('http') ? url : `${API_URL}${url}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError('network', 0);
  }

  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized?.();
    const code =
      typeof body?.detail?.code === 'string' ? body.detail.code : res.status === 422 ? 'validation' : 'unknown';
    throw new ApiError(code, res.status);
  }
  return body as T;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body ? JSON.stringify(body) : undefined });

export type PickedImage = { uri: string; mimeType?: string | null; fileName?: string | null; file?: File };

export const api = {
  register: (b: { email: string; password: string; name: string; locale: string }) =>
    request<{ token: string; user: User }>('/auth/register', json('POST', b)),
  login: (b: { email: string; password: string }) => request<{ token: string; user: User }>('/auth/login', json('POST', b)),
  demo: (locale: string) => request<{ token: string; user: User }>('/auth/demo', json('POST', { locale })),

  me: () => request<User>('/me'),
  updateMe: (b: Partial<Pick<User, 'name' | 'locale' | 'city' | 'lat' | 'lon'>>) => request<User>('/me', json('PATCH', b)),
  deleteMe: () => request<void>('/me', { method: 'DELETE' }),

  items: () => request<Item[]>('/items'),
  analyze: (img: PickedImage, lang: string) => {
    const form = new FormData();
    if (Platform.OS === 'web' && img.file) {
      form.append('image', img.file);
    } else {
      // React Native's FormData accepts { uri, name, type } for files.
      form.append('image', {
        uri: img.uri,
        name: img.fileName || 'photo.jpg',
        type: img.mimeType || 'image/jpeg',
      } as unknown as Blob);
    }
    form.append('lang', lang);
    return request<{ image_key: string; image_url: string; is_clothing: boolean; tags: Tags }>('/items/analyze', {
      method: 'POST',
      body: form,
    });
  },
  createItem: (b: Tags & { image_key: string }) => request<Item>('/items', json('POST', b)),
  updateItem: (id: string, b: Partial<Tags>) => request<Item>(`/items/${id}`, json('PATCH', b)),
  deleteItem: (id: string) => request<void>(`/items/${id}`, { method: 'DELETE' }),

  suggest: (b: { occasion: Occasion; note: string; lang: string; lat?: number; lon?: number }) =>
    request<{ weather: Weather | null; outfits: Outfit[] }>('/outfits/suggest', json('POST', b)),
  outfits: (likedOnly: boolean) => request<Outfit[]>(`/outfits${likedOnly ? '?liked_only=true' : ''}`),
  feedback: (id: string, rating: -1 | 0 | 1) => request<Outfit>(`/outfits/${id}/feedback`, json('POST', { rating })),

  weather: (lat: number, lon: number) => request<Weather>(`/weather?lat=${lat}&lon=${lon}`),
  cities: (q: string, lang: string) => request<City[]>(`/cities?q=${encodeURIComponent(q)}&lang=${lang}`),
};
