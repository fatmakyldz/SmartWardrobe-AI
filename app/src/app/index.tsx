import { Redirect } from 'expo-router';

import { useAuth } from '@/lib/auth';
import { takeFirstPieces } from '@/lib/onboarding';

export default function Index() {
  const { user } = useAuth();
  // Sign-up from "Start with 3 of my own pieces": the guard switch lands here, and here is the one
  // place that can send the new account to its first photo without racing the router.
  if (user && takeFirstPieces()) return <Redirect href={{ pathname: '/item/new', params: { first: '1' } }} />;
  return <Redirect href={user ? '/today' : '/welcome'} />;
}
