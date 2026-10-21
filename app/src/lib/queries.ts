import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, Intent, Item, Occasion, Outfit, Tags } from './api';

export const keys = {
  items: ['items'] as const,
  outfits: (liked: boolean) => ['outfits', liked] as const,
  // The last set from /outfits/suggest. Client-only: filled by useSuggest, never fetched.
  latestOutfits: ['outfits', 'latest'] as const,
  latestIntent: ['outfits', 'latest', 'intent'] as const, // what the last free-text request parsed to
  analysis: ['analysis'] as const,
};

// Saved lists (['outfits', true|false]) — everything under ['outfits'] except the client-only latest set.
function invalidateOutfitLists(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: ['outfits'], predicate: (q) => q.queryKey[1] !== 'latest' });
}

// Image links in responses live 15 minutes; refetching after 10 keeps them valid (§14 C4).
const IMAGE_LINK_STALE = 10 * 60 * 1000;

export function useItems() {
  return useQuery({ queryKey: keys.items, queryFn: api.items, staleTime: IMAGE_LINK_STALE });
}

// The same item from the wardrobe list, whose image link is the freshest one we have.
export function useFreshItem(item: Item): Item {
  const { data } = useItems();
  return data?.find((i) => i.id === item.id) ?? item;
}

export function useOutfits(liked: boolean, enabled = true) {
  return useQuery({ queryKey: keys.outfits(liked), queryFn: () => api.outfits(liked), staleTime: IMAGE_LINK_STALE, enabled });
}

export function useLatestOutfits() {
  return useQuery<Outfit[]>({
    queryKey: keys.latestOutfits,
    queryFn: () => [],
    enabled: false, // nothing to fetch; keeps invalidations and refocus from wiping it
    initialData: [],
    staleTime: Infinity,
    gcTime: Infinity, // survive tab switches; cleared with the rest of the cache on sign-out
  });
}

export function useSuggest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { occasion: Occasion; note: string; request?: string; lang: string }) => api.suggest(b),
    onSuccess: (res) => {
      qc.setQueryData<Outfit[]>(keys.latestOutfits, res.outfits);
      qc.setQueryData<Intent | null>(keys.latestIntent, res.intent);
      invalidateOutfitLists(qc);
    },
  });
}

export function useLatestIntent() {
  return useQuery<Intent | null>({
    queryKey: keys.latestIntent,
    queryFn: () => null,
    enabled: false,
    initialData: null,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** "Wore it today": the outfit comes back with worn_at; pieces' wear data changes too, so items refetch. */
export function useWorn() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.worn(id),
    onSuccess: (updated) => {
      qc.setQueryData<Outfit[]>(keys.latestOutfits, (list) => list && patchOutfit(list, updated));
      invalidateOutfitLists(qc);
      void qc.invalidateQueries({ queryKey: keys.items }); void qc.invalidateQueries({ queryKey: keys.analysis });
      void qc.invalidateQueries({ queryKey: keys.analysis });
    },
  });
}

export function useSaveOutfit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { id: string | null; item_ids: string[]; occasion: Occasion; title: string; lang: string }) =>
      b.id ? api.updateOutfitItems(b.id, b.item_ids) : api.createOutfit({ item_ids: b.item_ids, occasion: b.occasion, title: b.title, lang: b.lang }),
    onSuccess: (updated) => {
      qc.setQueryData<Outfit[]>(keys.latestOutfits, (list) => list && patchOutfit(list, updated));
      invalidateOutfitLists(qc);
    },
  });
}

export function useAnalysis(enabled = true) {
  return useQuery({ queryKey: keys.analysis, queryFn: api.analysis, enabled, staleTime: 5 * 60_000 });
}

export function useCreateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: Tags & { image_key: string }) => api.createItem(b),
    onSuccess: (item) => {
      qc.setQueryData<Item[]>(keys.items, (old) => [item, ...(old ?? [])]);
      void qc.invalidateQueries({ queryKey: keys.analysis });
    },
  });
}

export function useUpdateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...b }: Partial<Tags> & { id: string }) => api.updateItem(id, b),
    onSuccess: (item) => {
      qc.setQueryData<Item[]>(keys.items, (old) => old?.map((i) => (i.id === item.id ? item : i)));
      void qc.invalidateQueries({ queryKey: keys.analysis });
    },
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteItem(id),
    onSuccess: (_, id) => {
      qc.setQueryData<Item[]>(keys.items, (old) => old?.filter((i) => i.id !== id));
      qc.invalidateQueries({ queryKey: ['outfits'] });
      void qc.invalidateQueries({ queryKey: keys.analysis });
    },
  });
}

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rating }: { id: string; rating: -1 | 0 | 1 }) => api.feedback(id, rating),
    // Today shows the new rating at once; Saved waits for the refetch as before.
    onMutate: ({ id, rating }) => {
      const previous = qc.getQueryData<Outfit[]>(keys.latestOutfits);
      qc.setQueryData<Outfit[]>(keys.latestOutfits, (list) => list?.map((o) => (o.id === id ? { ...o, rating } : o)));
      return { previous };
    },
    onError: (_err, _vars, ctx) => qc.setQueryData(keys.latestOutfits, ctx?.previous),
    onSuccess: (updated) => {
      qc.setQueryData<Outfit[]>(keys.latestOutfits, (list) => list && patchOutfit(list, updated));
      invalidateOutfitLists(qc);
    },
  });
}

export function patchOutfit(list: Outfit[], updated: Outfit): Outfit[] {
  return list.map((o) => (o.id === updated.id ? updated : o));
}
