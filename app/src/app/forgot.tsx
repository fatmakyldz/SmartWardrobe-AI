import { useState } from 'react';

import { AuthPage } from '@/components/AuthPage';
import { Button, Field, Notice, T } from '@/components/ui';
import { api } from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';

export default function Forgot() {
  const { t } = useI18n();
  const errorText = useErrorText();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.forgot(email.trim());
      setSent(true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthPage title={t.auth.forgotTitle}>
      <T variant="body" color="muted">
        {t.auth.forgotIntro}
      </T>
      <Field
        label={t.auth.email}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
        onSubmitEditing={() => email.includes('@') && submit()}
      />
      {sent ? <Notice>{t.auth.forgotSent}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Button label={t.auth.forgotSend} onPress={submit} loading={busy} disabled={!email.includes('@')} />
    </AuthPage>
  );
}
