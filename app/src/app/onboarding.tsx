import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Button, Chip, Notice, Screen, T } from '@/components/ui';
import { api, Palette, PALETTES, PRIORITIES, Priority, Style, STYLES, StylePatch } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { clearPendingOnboarding, setPendingOnboarding } from '@/lib/onboarding';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

/**
 * Three style questions before any account exists (§10 step 1). The answers go with the demo request,
 * so the first suggestion already uses them; "Skip" opens a plain demo.
 */
export default function Onboarding() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const { signIn } = useAuth();
  const errorText = useErrorText();
  const [q1, setQ1] = useState<Style | null>(null);
  const [q2, setQ2] = useState<Palette[]>([]);
  const [q3, setQ3] = useState<Priority | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answered = (q1 ? 1 : 0) + (q2.length ? 1 : 0) + (q3 ? 1 : 0);
  const profile: StylePatch | undefined = answered === 0 ? undefined : { answers: { q1, q2: q2.length ? q2 : null, q3 } };

  /** "Start with my own pieces": sign up, then the first-pieces flow; the answers wait in memory and
   *  are saved right after the account exists (AuthForm). */
  function startOwn() {
    setPendingOnboarding(profile ?? null, true);
    router.push('/sign-up');
  }

  async function start(skip: boolean) {
    setBusy(true);
    setError(null);
    clearPendingOnboarding(); // the demo path: nothing waits for an account
    try {
      await signIn(await api.demo(lang, skip ? undefined : profile));
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  function togglePalette(x: Palette) {
    setQ2((cur) => (cur.includes(x) ? cur.filter((c) => c !== x) : [...cur, x]));
  }

  return (
    <Screen edges={['top', 'bottom']}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t.common.close}
        onPress={() => (router.canGoBack() ? router.back() : router.replace('/welcome'))}
        style={{ alignSelf: 'flex-start', paddingVertical: space.md }}
        hitSlop={12}
      >
        <CloseIcon color={p.ink} />
      </Pressable>

      <T variant="title" accessibilityRole="header" style={{ marginTop: space.lg }}>
        {t.onboarding.title}
      </T>
      <T variant="body" color="inkSoft" style={{ marginTop: space.sm }}>
        {t.onboarding.intro}
      </T>

      <View style={{ gap: space.xxl, marginTop: space.xxl }}>
        <View style={{ gap: space.md }}>
          <T variant="small" color="muted">
            {t.onboarding.step(1, 3)}
          </T>
          <T variant="heading">{t.onboarding.q1}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {STYLES.map((s) => (
              <Chip key={s} label={t.styleNames[s]} selected={q1 === s} onPress={() => setQ1(q1 === s ? null : s)} />
            ))}
          </View>
        </View>

        <View style={{ gap: space.md }}>
          <T variant="small" color="muted">
            {t.onboarding.step(2, 3)} · {t.onboarding.pickMany}
          </T>
          <T variant="heading">{t.onboarding.q2}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {PALETTES.map((x) => (
              <Chip key={x} label={t.paletteNames[x]} selected={q2.includes(x)} onPress={() => togglePalette(x)} />
            ))}
          </View>
        </View>

        <View style={{ gap: space.md }}>
          <T variant="small" color="muted">
            {t.onboarding.step(3, 3)}
          </T>
          <T variant="heading">{t.onboarding.q3}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {PRIORITIES.map((x) => (
              <Chip key={x} label={t.priorityNames[x]} selected={q3 === x} onPress={() => setQ3(q3 === x ? null : x)} />
            ))}
          </View>
        </View>
      </View>

      <View style={{ gap: space.md, marginTop: space.xxl }}>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Button label={t.onboarding.own} onPress={startOwn} disabled={busy} />
        <T variant="small" color="muted" style={{ textAlign: 'center' }}>
          {t.onboarding.ownHint}
        </T>
        <Button label={t.onboarding.go} kind="secondary" onPress={() => start(false)} loading={busy} />
        <T variant="small" color="muted" style={{ textAlign: 'center' }}>
          {t.welcome.demoNote}
        </T>
        <Button label={t.onboarding.skip} kind="ghost" onPress={() => start(true)} disabled={busy} />
      </View>
    </Screen>
  );
}
