import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// Keychain/Keystore on devices; localStorage on the web (SecureStore has no web implementation).
const KEY = 'sw.token';

export async function readToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return globalThis.localStorage?.getItem(KEY) ?? null;
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(KEY);
}

export async function writeToken(token: string | null): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      if (token) globalThis.localStorage?.setItem(KEY, token);
      else globalThis.localStorage?.removeItem(KEY);
    } catch {
      // storage blocked (private mode): session lasts until reload
    }
    return;
  }
  if (token) await SecureStore.setItemAsync(KEY, token);
  else await SecureStore.deleteItemAsync(KEY);
}
