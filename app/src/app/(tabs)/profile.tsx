import Constants from 'expo-constants';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Linking, Platform, View } from 'react-native';

import { CityPicker } from '@/components/CityPicker';
import { Button, Chip, Notice, Screen, T } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { Lang, useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

const PRIVACY_URL = process.env.EXPO_PUBLIC_PRIVACY_URL || 'https://fomertech.com';

function confirm(message: string, okLabel: string, cancelLabel: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(globalThis.confirm?.(message) ?? false);
  return new Promise((resolve) =>
    Alert.alert('', message, [
      { text: cancelLabel, style: 'cancel', onPress: () => resolve(false) },
      { text: okLabel, style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}

export default function Profile() {
  const p = usePalette();
  const { t, lang, setLang } = useI18n();
  const { user, setUser, signOut } = useAuth();
  const errorText = useErrorText();
  const [pickingCity, setPickingCity] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  if (!user) return null;

  async function changeLang(l: Lang) {
    setLang(l);
    try {
      setUser(await api.updateMe({ locale: l }));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function deleteAccount() {
    if (!(await confirm(t.profile.deleteConfirm, t.common.delete, t.common.cancel))) return;
    setDeleting(true);
    try {
      await api.deleteMe();
      await signOut();
    } catch (e) {
      setError(errorText(e));
      setDeleting(false);
    }
  }

  return (
    <Screen>
      <T variant="title" accessibilityRole="header" style={{ marginTop: space.xl }}>
        {user.is_demo ? t.profile.title : user.name || t.profile.title}
      </T>
      {!user.is_demo ? (
        <T variant="body" color="muted" style={{ marginTop: space.xs }}>
          {user.email}
        </T>
      ) : null}

      {user.is_demo ? (
        <View style={{ marginTop: space.xl, gap: space.md }}>
          <Notice>{t.profile.demoBanner}</Notice>
          <Button label={t.profile.createReal} onPress={() => router.push('/claim')} />
        </View>
      ) : null}

      <View style={{ marginTop: space.xxl, gap: space.md }}>
        <T variant="heading">{t.style.title}</T>
        <Button label={t.profile.stylePrefs} kind="secondary" onPress={() => router.push('/style')} />
      </View>

      <View style={{ marginTop: space.xxl, gap: space.md }}>
        <T variant="heading">{t.profile.city}</T>
        <T variant="body" color="inkSoft">
          {user.city || '—'}
        </T>
        {pickingCity ? (
          <CityPicker
            onPick={async (c) => {
              setPickingCity(false);
              try {
                setUser(await api.updateMe(c));
              } catch (e) {
                setError(errorText(e));
              }
            }}
          />
        ) : (
          <Button label={t.today.setCity} kind="secondary" onPress={() => setPickingCity(true)} />
        )}
      </View>

      <View style={{ marginTop: space.xxl, gap: space.md }}>
        <T variant="heading">{t.profile.language}</T>
        <View style={{ flexDirection: 'row', gap: space.sm }}>
          <Chip label="English" selected={lang === 'en'} onPress={() => changeLang('en')} />
          <Chip label="Türkçe" selected={lang === 'tr'} onPress={() => changeLang('tr')} />
        </View>
      </View>

      {error ? (
        <View style={{ marginTop: space.xl }}>
          <Notice tone="error">{error}</Notice>
        </View>
      ) : null}

      <View style={{ marginTop: space.xxxl, gap: space.md }}>
        <Button label={t.profile.signOut} kind="secondary" onPress={signOut} />
        <Button label={t.profile.privacy} kind="ghost" onPress={() => Linking.openURL(PRIVACY_URL)} />
        <Button label={t.profile.deleteAccount} kind="danger" onPress={deleteAccount} loading={deleting} />
        <T variant="tiny" color="muted" style={{ textAlign: 'center', marginTop: space.lg, color: p.muted }}>
          {t.profile.version(Constants.expoConfig?.version ?? '')}
        </T>
      </View>
    </Screen>
  );
}
