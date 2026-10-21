import Constants from 'expo-constants';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Platform, Share, View } from 'react-native';

import { CityPicker } from '@/components/CityPicker';
import { Button, Chip, Notice, Screen, T } from '@/components/ui';
import { api, FEATURES } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { Lang, useI18n } from '@/lib/i18n';
import { useEntitlements } from '@/lib/queries';
import { LANG_LABELS, SUPPORTED_LANGS } from '@/lib/langs';
import { space, usePalette } from '@/lib/theme';

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
  const [exporting, setExporting] = useState(false);
  const ent = useEntitlements(!!user).data;

  if (!user) return null;

  async function changeLang(l: Lang) {
    setLang(l);
    try {
      setUser(await api.updateMe({ locale: l }));
    } catch (e) {
      setError(errorText(e));
    }
  }

  // One JSON file with everything the account holds: a download on the web, the share sheet elsewhere.
  async function exportData() {
    setExporting(true);
    setError(null);
    try {
      const text = await api.exportData();
      if (Platform.OS === 'web') {
        const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = 'smartwardrobe-export.json';
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
      } else {
        await Share.share({ message: text, title: 'smartwardrobe-export.json' });
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setExporting(false);
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

      {ent ? (
        <View style={{ marginTop: space.xxl, padding: space.lg, borderRadius: 16, backgroundColor: p.surface, borderWidth: 1, borderColor: p.line, gap: space.sm }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <T variant="heading">{t.profile.plan}</T>
            <T variant="smallStrong" style={{ color: p.tapeInk, backgroundColor: p.tape, paddingHorizontal: 10, paddingVertical: 3, borderRadius: 10 }}>
              {t.profile.planNames[ent.plan] ?? ent.plan}
            </T>
          </View>
          <T variant="body" color="inkSoft">
            {t.profile.planPieces(ent.items_used, ent.max_items)}
          </T>
          <T variant="body" color="inkSoft">
            {t.profile.planRequests(ent.usage.requests_left, ent.daily_ai_requests)}
          </T>
          <T variant="small" color="muted" style={{ marginTop: space.xs }}>
            {t.profile.planFeatures}: {FEATURES.filter((f) => ent.features.includes(f)).map((f) => t.profile.featureNames[f]).join(' · ')}
          </T>
          {ent.plan !== 'premium' ? (
            <T variant="small" color="muted">
              {t.profile.premiumSoon}
            </T>
          ) : null}
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
          {SUPPORTED_LANGS.map((l) => (
            <Chip key={l} label={LANG_LABELS[l]} selected={lang === l} onPress={() => changeLang(l)} />
          ))}
        </View>
      </View>

      {error ? (
        <View style={{ marginTop: space.xl }}>
          <Notice tone="error">{error}</Notice>
        </View>
      ) : null}

      <View style={{ marginTop: space.xxxl, gap: space.md }}>
        <Button label={t.profile.signOut} kind="secondary" onPress={signOut} />
        <Button label={t.profile.exportData} kind="ghost" onPress={exportData} loading={exporting} />
        <Button label={t.profile.privacy} kind="ghost" onPress={() => router.push('/privacy')} />
        <Button label={t.profile.deleteAccount} kind="danger" onPress={deleteAccount} loading={deleting} />
        <T variant="tiny" color="muted" style={{ textAlign: 'center', marginTop: space.lg, color: p.muted }}>
          {t.profile.version(Constants.expoConfig?.version ?? '')}
        </T>
      </View>
    </Screen>
  );
}
