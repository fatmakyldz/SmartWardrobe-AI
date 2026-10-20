import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { AuthPage } from '@/components/AuthPage';
import { Button, Notice } from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { usePalette } from '@/lib/theme';

// Opened from the verification email: wardrobe.fomertech.com/auth/verify?token=… or smartwardrobe://auth/verify?token=…
// Works signed in or not (the link may open on another device).
export default function Verify() {
  const { token } = useLocalSearchParams<{ token?: string }>();
  const { t } = useI18n();
  const p = usePalette();
  const { user, setUser } = useAuth();
  const errorText = useErrorText();
  const [state, setState] = useState<'busy' | 'ok' | string>(token ? 'busy' : t.auth.missingToken);
  const sent = useRef(false); // the token is single use: never send it twice

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    api
      .verifyEmail(token)
      .then((verified) => {
        if (user && user.id === verified.id) setUser({ ...user, email_verified_at: verified.email_verified_at });
        setState('ok');
      })
      .catch((e) => setState(errorText(e)));
  }, [token, user, setUser, errorText]);

  return (
    <AuthPage title={t.auth.verifyTitle}>
      {state === 'busy' ? (
        <ActivityIndicator color={p.ink} style={{ alignSelf: 'flex-start' }} />
      ) : state === 'ok' ? (
        <Notice>{t.auth.verified}</Notice>
      ) : (
        <Notice tone="error">{state}</Notice>
      )}
      {state !== 'busy' ? (
        <Button label={user ? t.auth.continue : t.auth.backToSignIn} onPress={() => router.replace(user ? '/today' : '/sign-in')} />
      ) : null}
    </AuthPage>
  );
}
