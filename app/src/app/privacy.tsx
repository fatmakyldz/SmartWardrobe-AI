import { router } from 'expo-router';
import { Linking, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Screen, T } from '@/components/ui';
import { PRIVACY } from '@/content/privacy';
import { SUPPORT_EMAIL } from '@/lib/brand';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

/** The privacy policy: in the app for signed-in people, and the public page the stores link to on the web. */
export default function Privacy() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const policy = PRIVACY[lang];

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
        {policy.title}
      </T>
      <T variant="small" color="muted" style={{ marginTop: space.xs }}>
        {policy.updated}
      </T>
      <T variant="body" color="inkSoft" style={{ marginTop: space.lg }}>
        {policy.intro}
      </T>

      <View style={{ gap: space.xl, marginTop: space.xl }}>
        {policy.sections.map((s) => (
          <View key={s.heading} style={{ gap: space.sm }}>
            <T variant="heading" accessibilityRole="header">
              {s.heading}
            </T>
            {s.paragraphs.map((para) =>
              para === SUPPORT_EMAIL ? (
                <Pressable key={para} accessibilityRole="link" onPress={() => void Linking.openURL(`mailto:${SUPPORT_EMAIL}`)}>
                  <T variant="body" style={{ textDecorationLine: 'underline' }}>
                    {para}
                  </T>
                </Pressable>
              ) : (
                <T key={para} variant="body" color="inkSoft">
                  {para}
                </T>
              ),
            )}
          </View>
        ))}
      </View>
    </Screen>
  );
}
