import { useLocalSearchParams } from 'expo-router';

import { AuthForm } from '@/components/AuthForm';

export default function SignUp() {
  const { first } = useLocalSearchParams<{ first?: string }>();
  return <AuthForm mode="sign-up" firstPieces={first === '1'} />;
}
