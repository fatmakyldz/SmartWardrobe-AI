import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';

import { AuthPage } from '@/components/AuthPage';
import { Button, Field, Notice } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';

// Opened from the reset email: wardrobe.fomertech.com/auth/reset?token=… or smartwardrobe://auth/reset?token=…
export default function Reset() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  const { t } = useI18n();
  const { user, signOut } = useAuth();
  const errorText = useErrorText();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword({ token, password });
      setDone(true);
      if (user) await signOut(); // every session ended with the reset, this one too
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthPage title={t.auth.resetTitle}>
        <Notice tone="error">{t.auth.missingToken}</Notice>
      </AuthPage>
    );
  }

  return (
    <AuthPage title={t.auth.resetTitle}>
      {done ? (
        <>
          <Notice>{t.auth.resetDone}</Notice>
          <Button label={t.auth.backToSignIn} onPress={() => router.replace('/sign-in')} />
        </>
      ) : (
        <>
          <Field
            label={t.auth.newPassword}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
            textContentType="newPassword"
            hint={t.auth.passwordHint}
            onSubmitEditing={() => password.length >= 8 && submit()}
          />
          {error ? <Notice tone="error">{error}</Notice> : null}
          <Button label={t.auth.resetSave} onPress={submit} loading={busy} disabled={password.length < 8} />
        </>
      )}
    </AuthPage>
  );
}
