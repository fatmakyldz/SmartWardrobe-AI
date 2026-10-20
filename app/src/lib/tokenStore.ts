import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// The refresh token, in the Keychain/Keystore. The web keeps nothing here: its refresh token is an
// httpOnly cookie and the access token stays in memory.
const KEY = 'sw.refresh';
const OLD_KEY = 'sw.token'; // the 30-day token before AI-05; no longer accepted by the API

export async function readRefreshToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      globalThis.localStorage?.removeItem(OLD_KEY);
    } catch {
      // storage blocked (private mode)
    }
    return null;
  }
  void SecureStore.deleteItemAsync(OLD_KEY).catch(() => undefined);
  return SecureStore.getItemAsync(KEY);
}

export async function writeRefreshToken(token: string | null): Promise<void> {
  if (Platform.OS === 'web') return;
  if (token) await SecureStore.setItemAsync(KEY, token);
  else await SecureStore.deleteItemAsync(KEY);
}
