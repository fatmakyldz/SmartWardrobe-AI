import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, useWindowDimensions, View } from 'react-native';

import { Chip, Notice, Screen, T } from '@/components/ui';
import { OutfitBoard } from '@/components/wardrobe';
import { Outfit } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useAuth } from '@/lib/auth';
import { useI18n } from '@/lib/i18n';
import { useFeedback, useOutfits, useWorn } from '@/lib/queries';
import { space, usePalette } from '@/lib/theme';

export default function Saved() {
  const p = usePalette();
  const { t } = useI18n();
  const errorText = useErrorText();
  const { user } = useAuth();
  const [liked, setLiked] = useState(true);
  const outfits = useOutfits(liked);
  const feedback = useFeedback();
  const worn = useWorn();
  const { width } = useWindowDimensions();
  const boardWidth = Math.min(width, 720) - space.xl * 2;

  const rate = (o: Outfit, r: -1 | 1) => feedback.mutate({ id: o.id, rating: o.rating === r ? 0 : r });

  return (
    <Screen>
      <T variant="title" accessibilityRole="header" style={{ marginTop: space.xl }}>
        {t.saved.title}
      </T>
      <View style={{ flexDirection: 'row', gap: space.sm, marginTop: space.lg }}>
        <Chip label={t.saved.liked} selected={liked} onPress={() => setLiked(true)} />
        <Chip label={t.saved.all} selected={!liked} onPress={() => setLiked(false)} />
      </View>

      <View style={{ marginTop: space.xl, gap: space.xxl }}>
        {outfits.isLoading ? <ActivityIndicator color={p.ink} /> : null}
        {outfits.isError ? <Notice tone="error">{errorText(outfits.error)}</Notice> : null}
        {worn.isError ? <Notice tone="error">{errorText(worn.error)}</Notice> : null}
        {outfits.isSuccess && outfits.data.length === 0 ? (
          <T variant="body" color="inkSoft">
            {t.saved.empty}
          </T>
        ) : null}
        {outfits.data?.map((o) => (
          <OutfitBoard
            key={o.id}
            outfit={o}
            width={boardWidth}
            onRate={(r) => rate(o, r)}
            onOpenItem={(item) => router.push({ pathname: '/item/[id]', params: { id: item.id } })}
            onWorn={() => worn.mutate(o.id)}
            onEdit={user?.is_demo ? undefined : () => router.push({ pathname: '/outfit/[id]', params: { id: o.id } })}
          />
        ))}
      </View>
    </Screen>
  );
}
