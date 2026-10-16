import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, Item, Outfit, Tags } from './api';

export const keys = {
  items: ['items'] as const,
  outfits: (liked: boolean) => ['outfits', liked] as const,
};

export function useItems() {
  return useQuery({ queryKey: keys.items, queryFn: api.items });
}

export function useOutfits(liked: boolean) {
  return useQuery({ queryKey: keys.outfits(liked), queryFn: () => api.outfits(liked) });
}

export function useCreateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: Tags & { image_key: string }) => api.createItem(b),
    onSuccess: (item) => qc.setQueryData<Item[]>(keys.items, (old) => [item, ...(old ?? [])]),
  });
}

export function useUpdateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...b }: Partial<Tags> & { id: string }) => api.updateItem(id, b),
    onSuccess: (item) => qc.setQueryData<Item[]>(keys.items, (old) => old?.map((i) => (i.id === item.id ? item : i))),
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteItem(id),
    onSuccess: (_, id) => {
      qc.setQueryData<Item[]>(keys.items, (old) => old?.filter((i) => i.id !== id));
      qc.invalidateQueries({ queryKey: ['outfits'] });
    },
  });
}

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rating }: { id: string; rating: -1 | 0 | 1 }) => api.feedback(id, rating),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['outfits'] }),
  });
}

export function patchOutfit(list: Outfit[], updated: Outfit): Outfit[] {
  return list.map((o) => (o.id === updated.id ? updated : o));
}
