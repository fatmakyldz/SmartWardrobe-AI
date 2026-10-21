import { router } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, View } from 'react-native';

import { accessToken, api, ApiError, refreshSession } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

import { CloseIcon } from './icons';
import { Button, Chip, Field, Notice, Screen, T } from './ui';

/**
 * sign-in / sign-up, or "claim": sign-up from inside a demo account, carrying the demo's access token so
 * its style answers (and, with keepItems, the sample pieces and liked outfits) move to the new account.
 */
export function AuthForm({ mode }: { mode: 'sign-in' | 'sign-up' | 'claim' }) {
  const { t, lang } = useI18n();
  const p = usePalette();
  const { signIn } = useAuth();
  const errorText = useErrorText();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [keepItems, setKeepItems] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isClaim = mode === 'claim';
  const isUp = mode === 'sign-up' || isClaim;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      let claim = {};
      if (isClaim) {
        // The claim carries the demo's access token, which lives 15 minutes: get a fresh one first.
        const fresh = (await refreshSession().catch(() => null))?.access ?? accessToken();
        if (!fresh) throw new ApiError('invalid_demo_token', 400);
        claim = { claim_demo_token: fresh, keep_demo_items: keepItems };
      }
      const res = isUp
        ? await api.register({ email: email.trim(), password, name: name.trim(), locale: lang, ...claim })
        : await api.login({ email: email.trim(), password });
      await signIn(res);
      if (isClaim) router.replace('/'); // still signed in, so the guard doesn't move us: go to Today
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const valid = email.includes('@') && password.length >= (isUp ? 8 : 1);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen edges={['top', 'bottom']}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t.common.close}
          onPress={() => (router.canGoBack() ? router.back() : router.replace(isClaim ? '/' : '/welcome'))}
          style={{ alignSelf: 'flex-start', paddingVertical: space.md }}
          hitSlop={12}
        >
          <CloseIcon color={p.ink} />
        </Pressable>

        <T variant="title" accessibilityRole="header" style={{ marginTop: space.lg, marginBottom: isClaim ? space.sm : space.xl }}>
          {isClaim ? t.claim.title : isUp ? t.auth.signUpTitle : t.auth.signInTitle}
        </T>
        {isClaim ? (
          <T variant="body" color="inkSoft" style={{ marginBottom: space.xl }}>
            {t.claim.intro}
          </T>
        ) : null}

        <View style={{ gap: space.lg }}>
          {isClaim ? (
            <View style={{ gap: space.sm }}>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
                <Chip label={t.claim.keepItems} selected={keepItems} onPress={() => setKeepItems(true)} />
                <Chip label={t.claim.startEmpty} selected={!keepItems} onPress={() => setKeepItems(false)} />
              </View>
              {keepItems ? (
                <T variant="small" color="muted">
                  {t.claim.keepItemsHint}
                </T>
              ) : null}
            </View>
          ) : null}
          {isUp ? (
            <Field label={t.auth.name} value={name} onChangeText={setName} autoComplete="name" textContentType="name" />
          ) : null}
          <Field
            label={t.auth.email}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            textContentType="emailAddress"
          />
          <Field
            label={t.auth.password}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete={isUp ? 'new-password' : 'current-password'}
            textContentType={isUp ? 'newPassword' : 'password'}
            hint={isUp ? t.auth.passwordHint : undefined}
            onSubmitEditing={() => valid && submit()}
          />
          {error ? <Notice tone="error">{error}</Notice> : null}
          <Button label={isUp ? t.auth.signUp : t.auth.signIn} onPress={submit} loading={busy} disabled={!valid} />
          {!isUp ? <Button label={t.auth.forgot} kind="ghost" onPress={() => router.push('/forgot')} /> : null}
          {!isClaim ? (
            <Button
              label={isUp ? t.auth.haveAccount : t.auth.noAccount}
              kind="ghost"
              onPress={() => router.replace(isUp ? '/sign-in' : '/sign-up')}
            />
          ) : null}
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}
