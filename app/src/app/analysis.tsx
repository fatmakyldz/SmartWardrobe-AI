import { router } from 'expo-router';
import { ActivityIndicator, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Button, Notice, Screen, T } from '@/components/ui';
import { ItemTile } from '@/components/wardrobe';
import { Gap } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { useAnalysis, useItems } from '@/lib/queries';
import { space, usePalette } from '@/lib/theme';

/** What the wardrobe is missing (AI-06 `GET /items/analysis`): deterministic, no AI request, every plan. */
export default function Analysis() {
  const p = usePalette();
  const { t } = useI18n();
  const errorText = useErrorText();
  const analysis = useAnalysis();
  const items = useItems();
  const byId = new Map((items.data ?? []).map((i) => [i.id, i]));
  const a = analysis.data;

  function describe(g: Gap): string {
    const category = g.category ? t.categories[g.category].toLowerCase() : '';
    const occasion = g.occasion ? t.occasions[g.occasion].toLowerCase() : '';
    const season = g.season ? t.seasons[g.season as keyof typeof t.seasons] : '';
    return t.analysis.gap(g.code, category, occasion, season);
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
        {t.analysis.title}
      </T>

      {analysis.isLoading ? <ActivityIndicator color={p.ink} style={{ alignSelf: 'flex-start', marginTop: space.xl }} /> : null}
      {analysis.isError ? (
        <View style={{ marginTop: space.xl }}>
          <Notice tone="error">{errorText(analysis.error)}</Notice>
        </View>
      ) : null}

      {a ? (
        <View style={{ gap: space.xl, marginTop: space.lg }}>
          <View style={{ gap: space.xs }}>
            <T variant="body" color="inkSoft">
              {t.analysis.stats(a.items, a.outfits_possible)}
            </T>
            {a.items ? (
              <T variant="small" color="muted">
                {t.analysis.neutrals(Math.round(a.neutral_share * 100))}
              </T>
            ) : null}
          </View>

          {a.items === 0 ? (
            <Notice>{t.analysis.empty}</Notice>
          ) : a.gaps.length === 0 ? (
            <Notice>{t.analysis.nothing}</Notice>
          ) : (
            a.gaps.map((g, i) => (
              <View key={`${g.code}-${g.occasion ?? ''}-${g.category ?? ''}-${i}`} style={{ gap: space.sm }}>
                <T variant="small" color="muted">
                  {t.analysis.severity[g.severity]}
                </T>
                <T variant="body">{describe(g)}</T>
                {g.item_ids.length ? (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.xs }}>
                    {g.item_ids.map((id) => {
                      const item = byId.get(id);
                      return item ? (
                        <ItemTile
                          key={id}
                          item={item}
                          size={88}
                          onPress={() => router.push({ pathname: '/item/[id]', params: { id } })}
                        />
                      ) : null;
                    })}
                  </View>
                ) : null}
              </View>
            ))
          )}

          {a.items ? (
            <Button label={t.analysis.capsuleLink} kind="secondary" onPress={() => router.push('/capsule')} />
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
