import { Platform } from 'react-native';

import { Lang } from './langs';

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

// Onboarding answers and explicit style preferences: fixed vocabularies, like the backend's vocab.py.
export const STYLES = ['minimal', 'classic', 'casual', 'bold', 'sporty', 'romantic', 'streetwear', 'boho'] as const;
export const PALETTES = ['neutral', 'dark', 'vivid', 'pastel'] as const;
export const PRIORITIES = ['comfort', 'elegance', 'weather', 'variety'] as const;
export type Style = (typeof STYLES)[number];
export type Palette = (typeof PALETTES)[number];
export type Priority = (typeof PRIORITIES)[number];
export type StyleAnswers = { q1?: Style | null; q2?: Palette[] | null; q3?: Priority | null };
export type StyleProfile = {
  answers: StyleAnswers;
  liked_colors: string[];
  disliked_colors: string[];
  styles: string[];
  avoid: string[];
  summary: string | null;
};
export type StylePatch = Partial<Omit<StyleProfile, 'summary'>>;

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
  locale: string; // the server's list may be ahead of or behind the app's; toLang() narrows it
  city: string;
  lat: number | null;
  lon: number | null;
  is_demo: boolean;
  email_verified_at: string | null;
};

// access: 15-minute JWT. refresh: 30 days, single use; null on the web, where it is an httpOnly cookie.
export type Session = { access: string; refresh: string | null; user: User };

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

// image_url is a short-lived link (a fresh one in every response); image_key is stable and is the image cache key.
export type Item = Tags & { id: string; image_key: string; image_url: string; created_at: string };

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
  source: 'ai' | 'ai_edited' | 'user';
  worn_at: string | null;
};

/** A free-text request as the vocabulary values the backend understood (AI-06). */
export type Intent = {
  occasion: Occasion | null;
  include_categories: Category[];
  include_colors: string[];
  avoid_categories: Category[];
  avoid_colors: string[];
  avoid_patterns: string[];
  wants_outerwear: boolean | null;
  brief: string;
};

export type GapCode =
  | 'missing_category'
  | 'occasion_uncovered'
  | 'season_uncovered'
  | 'few_shoes'
  | 'low_neutrals'
  | 'orphan_items'
  | 'few_partners';
export type Gap = {
  code: GapCode;
  category: Category | null;
  occasion: Occasion | null;
  season: string | null;
  severity: 1 | 2 | 3;
  item_ids: string[];
};
export type WardrobeAnalysis = {
  season: string;
  items: number;
  per_category: Partial<Record<Category, number>>;
  outfits_possible: number;
  neutral_share: number;
  gaps: Gap[];
};
export type Capsule = {
  occasions: Occasion[];
  season: string;
  items: Item[];
  outfits_possible: number;
  sample_outfits: string[][];
  gaps: Gap[];
  summary: string | null;
  tips: string[];
};

export type City = { name: string | null; label: string; lat: number; lon: number };

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code);
  }
}

const WEB = Platform.OS === 'web';

// The access token lives only in memory. The refresh token is kept by auth.tsx (SecureStore) on
// devices; on the web the browser keeps it as a cookie the page can't read.
let token: string | null = null;
let refreshToken: string | null = null;
let onUnauthorized: (() => void) | null = null;
let onRefreshed: ((s: Session) => void) | null = null;

/** The current access token, for a request body that must carry it (claiming a demo account). */
export function accessToken(): string | null {
  return token;
}

export function setSession(s: { access: string | null; refresh: string | null }) {
  token = s.access;
  refreshToken = s.refresh;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}
export function setRefreshedHandler(fn: (s: Session) => void) {
  onRefreshed = fn;
}

// expo-image source for a photo. The cache is keyed on image_key, so a new link for the same photo is
// a cache hit. Database storage mode serves /images from the API to the signed-in owner only, so those
// requests carry the token; presigned bucket links are signed already (an extra header would break them).
export function imageSource(url: string, key?: string): { uri: string; cacheKey?: string; headers?: Record<string, string> } {
  const uri = url.startsWith('http') ? url : `${API_URL}${url}`;
  const fromApi = uri.startsWith(`${API_URL}/images/`);
  return { uri, cacheKey: key, headers: fromApi && token ? { Authorization: `Bearer ${token}` } : undefined };
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const auth = path.startsWith('/auth/');
  // Web sign-in/refresh/logout: the refresh token travels as an httpOnly cookie (same site as the API).
  if (WEB && auth) headers['X-Auth-Cookie'] = '1';

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: WEB && auth ? 'include' : 'same-origin' });
  } catch {
    throw new ApiError('network', 0);
  }

  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const code =
      typeof body?.detail?.code === 'string' ? body.detail.code : res.status === 422 ? 'validation' : 'unknown';
    throw new ApiError(code, res.status);
  }
  return body as T;
}

// One refresh at a time: parallel 401s wait for the same call (a spent refresh token used twice
// would sign every device out).
let refreshing: Promise<Session | null> | null = null;

export function refreshSession(): Promise<Session | null> {
  if (!WEB && !refreshToken) return Promise.resolve(null);
  refreshing ??= (async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const s = await send<Session>('/auth/refresh', json('POST', WEB ? undefined : { refresh: refreshToken }));
        setSession(s);
        onRefreshed?.(s);
        return s;
      } catch (e) {
        // Another tab rotated the cookie a moment ago: the browser now holds the new one.
        if (WEB && e instanceof ApiError && e.code === 'refresh_superseded' && attempt === 0) {
          await new Promise((r) => setTimeout(r, 400));
          continue;
        }
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    }
    return null;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

// 401 → refresh once → retry; still 401 (or no session to refresh) → sign out.
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await send<T>(path, init);
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401 || !token || path.startsWith('/auth/')) throw e;
    const s = await refreshSession().catch(() => null);
    if (!s) {
      onUnauthorized?.();
      throw e;
    }
    try {
      return await send<T>(path, init);
    } catch (again) {
      if (again instanceof ApiError && again.status === 401) onUnauthorized?.();
      throw again;
    }
  }
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body ? JSON.stringify(body) : undefined });

export type PickedImage = { uri: string; mimeType?: string | null; fileName?: string | null; file?: File };

export const api = {
  register: (b: {
    email: string;
    password: string;
    name: string;
    locale: Lang;
    claim_demo_token?: string;
    keep_demo_items?: boolean;
  }) => request<Session & { claimed: Record<string, number | boolean> | null }>('/auth/register', json('POST', b)),
  login: (b: { email: string; password: string }) => request<Session>('/auth/login', json('POST', b)),
  demo: (locale: Lang, style_profile?: StylePatch) =>
    request<Session>('/auth/demo', json('POST', style_profile ? { locale, style_profile } : { locale })),
  logout: () => request<void>('/auth/logout', json('POST', WEB ? undefined : { refresh: refreshToken })),
  verifyEmail: (t: string) => request<User>('/auth/verify', json('POST', { token: t })),
  resendVerification: () => request<void>('/auth/resend-verification', { method: 'POST' }),
  forgot: (email: string) => request<{ status: string }>('/auth/forgot', json('POST', { email })),
  resetPassword: (b: { token: string; password: string }) => request<void>('/auth/reset', json('POST', b)),

  me: () => request<User>('/me'),
  updateMe: (b: Partial<Pick<User, 'name' | 'locale' | 'city' | 'lat' | 'lon'>>) => request<User>('/me', json('PATCH', b)),
  deleteMe: () => request<void>('/me', { method: 'DELETE' }),
  style: () => request<StyleProfile>('/me/style'),
  updateStyle: (b: StylePatch) => request<StyleProfile>('/me/style', json('PATCH', b)),

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
    return request<{
      image_key: string;
      image_url: string;
      is_clothing: boolean;
      tags: Tags;
      ai_skipped: string | null;
      confidence: number | null;
      uncertain: (keyof Tags)[];
    }>('/items/analyze', {
      method: 'POST',
      body: form,
    });
  },
  createItem: (b: Tags & { image_key: string; ai_confidence?: number | null }) => request<Item>('/items', json('POST', b)),
  updateItem: (id: string, b: Partial<Tags>) => request<Item>(`/items/${id}`, json('PATCH', b)),
  deleteItem: (id: string) => request<void>(`/items/${id}`, { method: 'DELETE' }),

  suggest: (b: { occasion: Occasion; note: string; request?: string; lang: string; lat?: number; lon?: number }) =>
    request<{ weather: Weather | null; outfits: Outfit[]; intent: Intent | null }>('/outfits/suggest', json('POST', b)),
  outfits: (likedOnly: boolean) => request<Outfit[]>(`/outfits${likedOnly ? '?liked_only=true' : ''}`),
  feedback: (id: string, rating: -1 | 0 | 1) => request<Outfit>(`/outfits/${id}/feedback`, json('POST', { rating })),
  worn: (id: string) => request<Outfit>(`/outfits/${id}/worn`, { method: 'POST' }),
  createOutfit: (b: { item_ids: string[]; occasion: Occasion; title?: string; lang: string }) =>
    request<Outfit>('/outfits', json('POST', b)),
  updateOutfitItems: (id: string, item_ids: string[]) => request<Outfit>(`/outfits/${id}/items`, json('PATCH', { item_ids })),
  analysis: () => request<WardrobeAnalysis>('/items/analysis'),
  capsule: (b: { occasions: Occasion[]; size: number; lang: string; explain: boolean }) =>
    request<Capsule>('/outfits/capsule', json('POST', b)),

  weather: (lat: number, lon: number) => request<Weather>(`/weather?lat=${lat}&lon=${lon}`),
  cities: (q: string, lang: string) => request<City[]>(`/cities?q=${encodeURIComponent(q)}&lang=${lang}`),
};
