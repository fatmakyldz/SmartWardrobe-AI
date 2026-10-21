import { Image } from 'expo-image';
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, useWindowDimensions, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Button, Chip, Field, Notice, Screen, T, tap } from '@/components/ui';
import { Category, CATEGORIES, imageSource, Item, Occasion, OCCASIONS, Outfit } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { keys, useItems, useOutfits, useSaveOutfit } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';
import { useQueryClient } from '@tanstack/react-query';

/** The rule the backend enforces (outfit_rules.py): top + bottom or a dress; one per category, accessories aside. */
function complete(items: Item[]): boolean {
  const cats = new Set(items.map((i) => i.category));
  return cats.has('dress') || (cats.has('top') && cats.has('bottom'));
}

/**
 * Edit an outfit's pieces (`/outfit/<id>`, an AI suggestion becomes ai_edited) or build one from the
 * wardrobe (`/outfit/new`). Selection is per category: tapping a piece swaps the category's piece,
 * accessories stack.
 */
export default function OutfitEditor() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const errorText = useErrorText();
  const qc = useQueryClient();
  const { id } = useLocalSearchParams<{ id: string }>();
  const isNew = id === 'new';
  const { width } = useWindowDimensions();

  const items = useItems();
  const history = useOutfits(false, !isNew);
  const existing: Outfit | undefined = useMemo(() => {
    if (isNew) return undefined;
    const latest = qc.getQueryData<Outfit[]>(keys.latestOutfits) ?? [];
    return [...latest, ...(history.data ?? []), ...(qc.getQueryData<Outfit[]>(keys.outfits(true)) ?? [])].find((o) => o.id === id);
  }, [isNew, id, history.data, qc]);

  const [selected, setSelected] = useState<string[] | null>(null);
  const chosen = selected ?? existing?.items.map((i) => i.id) ?? [];
  const [occasion, setOccasion] = useState<Occasion>('casual');
  const [title, setTitle] = useState('');
  const save = useSaveOutfit();

  const byId = new Map((items.data ?? []).map((i) => [i.id, i]));
  const chosenItems = chosen.map((x) => byId.get(x)).filter((x): x is Item => !!x);
  const ok = complete(chosenItems);

  const content = Math.min(width, 720) - space.xl * 2;
  const columns = content > 520 ? 5 : 4;
  const tile = (content - space.sm * (columns - 1)) / columns;

  function toggle(item: Item) {
    tap();
    setSelected((cur) => {
      const list = cur ?? chosen;
      if (list.includes(item.id)) return list.filter((x) => x !== item.id);
      if (item.category === 'accessory') return [...list, item.id];
      // one piece per category: the new one replaces the old
      return [...list.filter((x) => byId.get(x)?.category !== item.category), item.id];
    });
  }

  async function submit() {
    try {
      await save.mutateAsync({ id: isNew ? null : id, item_ids: chosen, occasion, title: title.trim(), lang });
      router.back();
    } catch {
      // shown below
    }
  }

  const grouped = CATEGORIES.map((c) => ({ c, list: (items.data ?? []).filter((i) => i.category === c) })).filter(
    (g) => g.list.length,
  );

  return (
    <Screen edges={['top', 'bottom']}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t.common.close}
        onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
        style={{ alignSelf: 'flex-start', paddingVertical: space.md }}
        hitSlop={12}
      >
        <CloseIcon color={p.ink} />
      </Pressable>

      <T variant="title" accessibilityRole="header" style={{ marginTop: space.lg }}>
        {isNew ? t.outfitEdit.newTitle : t.outfitEdit.title}
      </T>
      <T variant="body" color="inkSoft" style={{ marginTop: space.sm }}>
        {t.outfitEdit.intro}
      </T>

      {isNew ? (
        <View style={{ gap: space.lg, marginTop: space.xl }}>
          <Field label={t.outfitEdit.name} value={title} onChangeText={setTitle} maxLength={120} />
          <View style={{ gap: space.md }}>
            <T variant="heading">{t.outfitEdit.occasion}</T>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
              {OCCASIONS.map((o) => (
                <Chip key={o} label={t.occasions[o]} selected={occasion === o} onPress={() => setOccasion(o)} />
              ))}
            </View>
          </View>
        </View>
      ) : null}

      {items.isLoading || (!isNew && !existing && history.isLoading) ? (
        <ActivityIndicator color={p.ink} style={{ alignSelf: 'flex-start', marginTop: space.xl }} />
      ) : null}
      {items.isError ? <Notice tone="error">{errorText(items.error)}</Notice> : null}

      <View style={{ gap: space.xl, marginTop: space.xl }}>
        {grouped.map(({ c, list }) => (
          <View key={c} style={{ gap: space.sm }}>
            <T variant="heading">{t.categories[c as Category]}</T>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
              {list.map((item) => {
                const on = chosen.includes(item.id);
                return (
                  <Pressable
                    key={item.id}
                    accessibilityRole="button"
                    accessibilityState={{ selected: on }}
                    accessibilityLabel={item.name || t.categories[item.category]}
                    onPress={() => toggle(item)}
                    style={{
                      width: tile,
                      height: tile,
                      borderRadius: radius.md,
                      borderWidth: 3,
                      borderColor: on ? p.tape : 'transparent',
                      backgroundColor: p.surfaceAlt,
                      overflow: 'hidden',
                      opacity: on ? 1 : 0.9,
                    }}
                  >
                    <Image source={imageSource(item.image_url, item.image_key)} style={{ flex: 1 }} contentFit="cover" />
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}
      </View>

      <View style={{ gap: space.md, marginTop: space.xxl }}>
        <T variant="small" color="muted">
          {t.outfitEdit.selected(chosen.length)}
          {!ok && chosen.length ? ` · ${t.outfitEdit.incomplete}` : ''}
        </T>
        {save.isError ? <Notice tone="error">{errorText(save.error)}</Notice> : null}
        <Button label={t.outfitEdit.save} onPress={submit} loading={save.isPending} disabled={!ok} />
      </View>
    </Screen>
  );
}
