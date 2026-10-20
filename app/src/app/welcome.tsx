import { Image } from 'expo-image';
import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { Button, Notice, Screen, T } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { APP_NAME } from '@/lib/brand';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { radius, space, type, usePalette } from '@/lib/theme';

// Four pieces from the sample wardrobe, laid out like the outfit board.
const PREVIEW = [
  { src: require('../../assets/preview/navy-blazer.png'), tilt: '-4deg' },
  { src: require('../../assets/preview/oxford-shirt.png'), tilt: '3deg' },
  { src: require('../../assets/preview/beige-chinos.png'), tilt: '-2deg' },
  { src: require('../../assets/preview/brown-boots.png'), tilt: '4deg' },
];

export default function Welcome() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const { signIn } = useAuth();
  const errorText = useErrorText();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function tryDemo() {
    setBusy(true);
    setError(null);
    try {
      await signIn(await api.demo(lang));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={[styles.board, { backgroundColor: p.board }]}>
        {PREVIEW.map((pc, i) => (
          <View key={i} style={[styles.piece, { backgroundColor: p.surface, transform: [{ rotate: pc.tilt }] }]}>
            <Image source={pc.src} style={{ flex: 1, borderRadius: radius.sm }} contentFit="cover" />
          </View>
        ))}
      </View>

      <T variant="display" accessibilityRole="header" style={{ marginTop: space.xxl }}>
        {APP_NAME}
      </T>
      <T variant="heading" color="inkSoft" style={{ marginTop: space.sm, fontFamily: type.body.fontFamily }}>
        {t.welcome.tagline}
      </T>

      <View style={{ gap: space.md, marginTop: space.xl }}>
        {t.welcome.points.map((line) => (
          <View key={line} style={{ flexDirection: 'row', gap: space.md }}>
            <View style={[styles.stitch, { backgroundColor: p.tape }]} />
            <T variant="body" color="inkSoft" style={{ flex: 1 }}>
              {line}
            </T>
          </View>
        ))}
      </View>

      <View style={{ gap: space.md, marginTop: space.xxl }}>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Button label={t.welcome.demo} onPress={tryDemo} loading={busy} />
        <T variant="small" color="muted" style={{ textAlign: 'center' }}>
          {t.welcome.demoNote}
        </T>
        <View style={{ flexDirection: 'row', gap: space.md, marginTop: space.sm }}>
          <Button label={t.welcome.signIn} kind="secondary" style={{ flex: 1 }} onPress={() => router.push('/sign-in')} />
          <Button label={t.welcome.signUp} kind="secondary" style={{ flex: 1 }} onPress={() => router.push('/sign-up')} />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  board: {
    marginTop: space.xl,
    borderRadius: radius.lg,
    padding: space.lg,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    rowGap: space.md,
  },
  piece: {
    width: '47%',
    aspectRatio: 1,
    padding: 5,
    borderRadius: radius.sm + 2,
    shadowColor: '#2A1B26',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
    elevation: 3,
  },
  stitch: { width: 14, height: 3, borderRadius: 2, marginTop: 11 },
});
