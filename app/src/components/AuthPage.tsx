import { router } from 'expo-router';
import { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, View } from 'react-native';

import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

import { CloseIcon } from './icons';
import { Screen, T } from './ui';

// The frame shared by the forgot / reset / verify screens: close button, title, content.
export function AuthPage({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useI18n();
  const p = usePalette();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
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
        <T variant="title" accessibilityRole="header" style={{ marginTop: space.lg, marginBottom: space.xl }}>
          {title}
        </T>
        <View style={{ gap: space.lg }}>{children}</View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
