import { useMutation, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, useWindowDimensions, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Button, Chip, Notice, Screen, T, tap } from '@/components/ui';
import { ItemTile } from '@/components/wardrobe';
import { api, ApiError, Occasion, OCCASIONS } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { invalidateUsage } from '@/lib/queries';
import { space, usePalette } from '@/lib/theme';

/**
 * Capsule wardrobe (AI-06 `POST /outfits/capsule`, premium): the pieces are chosen deterministically on
 * the server, the model only writes the summary and tips. Shown as a plain list of the pieces, the
 * example outfits by name, the gaps and the tips.
 */
export default function CapsuleScreen() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const errorText = useErrorText();
  const { width } = useWindowDimensions();
  const [occasions, setOccasions] = useState<Occasion[]>(['casual', 'work']);
  const [size, setSize] = useState(12);

  // The explanation is the only AI spend: with today's budget gone, fall back to the deterministic
  // capsule (pieces, outfits, gaps) and say why there is no summary.
  const qc = useQueryClient();
  const build = useMutation({
    onSettled: () => void invalidateUsage(qc), // capsule_explain is request-counted
    mutationFn: async () => {
      try {
        return { ...(await api.capsule({ occasions, size, lang, explain: true })), budget: false };
      } catch (e) {
        if (e instanceof ApiError && e.code === 'budget_exceeded') {
          return { ...(await api.capsule({ occasions, size, lang, explain: false })), budget: true };
        }
        throw e;
      }
    },
  });
  const c = build.data;
  const notAllowed = build.error instanceof ApiError && build.error.code === 'feature_not_allowed';

  const content = Math.min(width, 720) - space.xl * 2;
  const columns = content > 520 ? 5 : 4;
  const tile = (content - space.sm * (columns - 1)) / columns;
  const byId = new Map((c?.items ?? []).map((i) => [i.id, i]));

  function toggleOccasion(o: Occasion) {
    setOccasions((cur) => (cur.includes(o) ? (cur.length > 1 ? cur.filter((x) => x !== o) : cur) : [...cur, o]));
  }

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
        {t.capsule.title}
      </T>
      <T variant="body" color="inkSoft" style={{ marginTop: space.sm }}>
        {t.capsule.intro}
      </T>

      <View style={{ gap: space.lg, marginTop: space.xl }}>
        <View style={{ gap: space.md }}>
          <T variant="heading">{t.capsule.occasions}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {OCCASIONS.map((o) => (
              <Chip key={o} label={t.occasions[o]} selected={occasions.includes(o)} onPress={() => toggleOccasion(o)} />
            ))}
          </View>
        </View>
        <View style={{ gap: space.md }}>
          <T variant="heading">{t.capsule.size}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {[8, 12, 16, 20].map((n) => (
              <Chip key={n} label={t.outfitEdit.selected(n)} selected={size === n} onPress={() => setSize(n)} />
            ))}
          </View>
        </View>
        {notAllowed ? (
          <Notice>{t.capsule.premium}</Notice>
        ) : build.isError ? (
          <Notice tone="error">{errorText(build.error)}</Notice>
        ) : null}
        <Button
          label={build.isPending ? t.capsule.building : t.capsule.build}
          loading={build.isPending}
          onPress={() => {
            tap();
            build.mutate();
          }}
        />
      </View>

      {c ? (
        <View style={{ gap: space.xl, marginTop: space.xxl }}>
          <T variant="heading">{t.capsule.result(c.items.length, c.outfits_possible)}</T>
          {c.budget ? <Notice>{t.errors.budget_exceeded}</Notice> : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, rowGap: space.md }}>
            {c.items.map((item) => (
              <ItemTile key={item.id} item={item} size={tile} onPress={() => router.push({ pathname: '/item/[id]', params: { id: item.id } })} />
            ))}
          </View>

          {c.summary ? (
            <T variant="body" color="inkSoft">
              {c.summary}
            </T>
          ) : null}

          {c.tips.length ? (
            <View style={{ gap: space.sm }}>
              <T variant="heading">{t.capsule.tips}</T>
              {c.tips.map((tip, i) => (
                <View key={i} style={{ flexDirection: 'row', gap: space.md }}>
                  <View style={{ width: 14, height: 3, borderRadius: 2, marginTop: 11, backgroundColor: p.tape }} />
                  <T variant="body" color="inkSoft" style={{ flex: 1 }}>
                    {tip}
                  </T>
                </View>
              ))}
            </View>
          ) : null}

          {c.sample_outfits.length ? (
            <View style={{ gap: space.sm }}>
              <T variant="heading">{t.capsule.examples}</T>
              {c.sample_outfits.slice(0, 6).map((ids, i) => (
                <T key={i} variant="body" color="inkSoft">
                  {ids
                    .map((id) => byId.get(id))
                    .filter((x) => !!x)
                    .map((x) => x!.name || t.categories[x!.category])
                    .join(' + ')}
                </T>
              ))}
            </View>
          ) : null}

          {c.gaps.filter((g) => g.category && g.code !== 'orphan_items').length ? (
            <View style={{ gap: space.sm }}>
              <T variant="heading">{t.capsule.missing}</T>
              <T variant="body" color="inkSoft">
                {[...new Set(c.gaps.filter((g) => g.category && g.code !== 'orphan_items').map((g) => g.category!))]
                  .map((cat) => t.categories[cat])
                  .join(' \u00b7 ')}
              </T>
            </View>
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
