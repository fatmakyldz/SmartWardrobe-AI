import {
  BricolageGrotesque_300Light,
  BricolageGrotesque_400Regular,
  BricolageGrotesque_500Medium,
  BricolageGrotesque_600SemiBold,
  BricolageGrotesque_700Bold,
  BricolageGrotesque_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/bricolage-grotesque';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundaryProps, Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform, Pressable, Text, useColorScheme, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiError } from '@/lib/api';
import { AuthProvider, useAuth } from '@/lib/auth';
import { I18nProvider } from '@/lib/i18n';
import { usePalette } from '@/lib/theme';

void SplashScreen.preventAutoHideAsync();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

function Root() {
  const p = usePalette();
  const scheme = useColorScheme();
  const { ready, user } = useAuth();
  const [fontsLoaded, fontError] = useFonts({
    BricolageGrotesque_300Light,
    BricolageGrotesque_400Regular,
    BricolageGrotesque_500Medium,
    BricolageGrotesque_600SemiBold,
    BricolageGrotesque_700Bold,
    BricolageGrotesque_800ExtraBold,
  });

  // A font that fails or times out (expo-font gives up after 12 s) falls back to the system font:
  // waiting for it forever left a blank page. The web doesn't wait at all: iOS Safari can sit on
  // the font load for the whole 12 s, and the browser swaps the font in once it arrives.
  const fontsDone = fontsLoaded || !!fontError || Platform.OS === 'web';

  useEffect(() => {
    if (ready && fontsDone) void SplashScreen.hideAsync();
  }, [ready, fontsDone]);

  if (!ready || !fontsDone) return null;

  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: p.bg } }}>
        <Stack.Screen name="index" />
        {/* Links from emails: open whether or not someone is signed in on this device. */}
        <Stack.Screen name="auth/verify" />
        <Stack.Screen name="auth/reset" />
        <Stack.Protected guard={!user}>
          <Stack.Screen name="welcome" />
          <Stack.Screen name="onboarding" />
          <Stack.Screen name="sign-in" />
          <Stack.Screen name="sign-up" />
          <Stack.Screen name="forgot" />
        </Stack.Protected>
        <Stack.Protected guard={!!user}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="claim" />
          <Stack.Screen name="style" options={{ presentation: 'modal' }} />
          <Stack.Screen name="outfit/[id]" options={{ presentation: 'modal' }} />
          <Stack.Screen name="analysis" options={{ presentation: 'modal' }} />
          <Stack.Screen name="capsule" options={{ presentation: 'modal' }} />
          <Stack.Screen name="item/new" options={{ presentation: 'modal' }} />
          <Stack.Screen name="item/[id]" options={{ presentation: 'modal' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

// Last resort: a render error anywhere shows its message instead of a blank page. Outside the
// providers, so plain components and both languages.
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  void SplashScreen.hideAsync();
  return (
    <View style={{ flex: 1, justifyContent: 'center', padding: 24, gap: 16, backgroundColor: '#ECE8E3' }}>
      <Text style={{ fontSize: 18, color: '#2a1b26' }}>Something went wrong. / Bir şeyler ters gitti.</Text>
      <Text selectable style={{ fontSize: 13, color: '#6b5a66' }}>
        {error.name}: {error.message}
      </Text>
      <Pressable accessibilityRole="button" onPress={() => void retry()} style={{ alignSelf: 'flex-start', paddingVertical: 8 }}>
        <Text style={{ fontSize: 16, color: '#4b2e45', textDecorationLine: 'underline' }}>Try again / Tekrar dene</Text>
      </Pressable>
    </View>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <AuthProvider>
            <Root />
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
