import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { PlusIcon } from '@/components/icons';
import { Button, Chip, Notice, T, tap } from '@/components/ui';
import { ItemTile } from '@/components/wardrobe';
import { Category, CATEGORIES } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { useHasFeature, useItems } from '@/lib/queries';
import { radius, space, usePalette } from '@/lib/theme';

export default function Wardrobe() {
  const p = usePalette();
  const { t } = useI18n();
  const errorText = useErrorText();
  const canBuild = useHasFeature('user_outfits') === true;
  const items = useItems();
  const [filter, setFilter] = useState<Category | 'all'>('all');
  const { width } = useWindowDimensions();

  const content = Math.min(width, 720) - space.xl * 2;
  const columns = content > 520 ? 4 : 3;
  const tile = (content - space.md * (columns - 1)) / columns;

  const list = useMemo(
    () => (items.data ?? []).filter((i) => filter === 'all' || i.category === filter),
    [items.data, filter],
  );
  const present = new Set((items.data ?? []).map((i) => i.category));

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: p.bg }}>
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: space.xl, paddingBottom: 120, width: '100%', maxWidth: 720, alignSelf: 'center' }}
        refreshControl={<RefreshControl refreshing={items.isRefetching} onRefresh={() => void items.refetch()} tintColor={p.ink} />}
      >
        <View style={{ marginTop: space.xl, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <T variant="title" accessibilityRole="header">
            {t.wardrobe.title}
          </T>
          {items.data ? (
            <T variant="small" color="muted">
              {t.wardrobe.count(items.data.length)}
            </T>
          ) : null}
        </View>

        {items.data?.length ? (
          <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.md }}>
            <Button label={t.analysis.link} kind="ghost" onPress={() => router.push('/analysis')} style={{ flex: 1 }} />
            {canBuild ? (
              <Button label={t.outfitEdit.newTitle} kind="ghost" onPress={() => router.push({ pathname: '/outfit/[id]', params: { id: 'new' } })} style={{ flex: 1 }} />
            ) : null}
          </View>
        ) : null}

        {items.data?.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: space.lg, marginHorizontal: -space.xl }}>
            <View style={{ flexDirection: 'row', gap: space.sm, paddingHorizontal: space.xl }}>
              <Chip label={t.wardrobe.all} selected={filter === 'all'} onPress={() => setFilter('all')} />
              {CATEGORIES.filter((c) => present.has(c)).map((c) => (
                <Chip key={c} label={t.categories[c]} selected={filter === c} onPress={() => setFilter(c)} />
              ))}
            </View>
          </ScrollView>
        ) : null}

        <View style={{ marginTop: space.xl }}>
          {items.isLoading ? <ActivityIndicator color={p.ink} /> : null}
          {items.isError ? <Notice tone="error">{errorText(items.error)}</Notice> : null}
          {items.isSuccess && items.data.length === 0 ? (
            <View style={{ gap: space.lg }}>
              <T variant="body" color="inkSoft">
                {t.wardrobe.empty}
              </T>
              <Button label={t.wardrobe.add} onPress={() => router.push('/item/new')} />
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.md, rowGap: space.lg }}>
            {list.map((item) => (
              <ItemTile
                key={item.id}
                item={item}
                size={tile}
                onPress={() => router.push({ pathname: '/item/[id]', params: { id: item.id } })}
              />
            ))}
          </View>
        </View>
      </ScrollView>

      {items.data?.length ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t.wardrobe.add}
          onPress={() => {
            tap();
            router.push('/item/new');
          }}
          style={({ pressed }) => ({
            position: 'absolute',
            right: space.xl,
            bottom: space.xl,
            width: 60,
            height: 60,
            borderRadius: radius.pill,
            backgroundColor: p.tape,
            alignItems: 'center',
            justifyContent: 'center',
            opacity: pressed ? 0.85 : 1,
            shadowColor: '#2A1B26',
            shadowOpacity: 0.2,
            shadowRadius: 10,
            shadowOffset: { width: 0, height: 4 },
            elevation: 5,
          })}
        >
          <PlusIcon color={p.tapeInk} size={28} />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}
