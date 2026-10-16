import * as Location from 'expo-location';
import { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';

import { api, ApiError, City } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

import { Button, Field, Notice, T, tap } from './ui';

export function CityPicker({ onPick }: { onPick: (c: { city: string; lat: number; lon: number }) => void }) {
  const { t, lang } = useI18n();
  const p = usePalette();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<City[]>([]);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) return;
    const id = setTimeout(() => {
      api
        .cities(q.trim(), lang)
        .then(setResults)
        .catch((e) => setError(t.errors[(e as ApiError).code as keyof typeof t.errors] ?? t.errors.unknown));
    }, 300);
    return () => clearTimeout(id);
  }, [q, lang, t]);

  async function useMyLocation() {
    setError(null);
    setLocating(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) return;
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low });
      const { latitude: lat, longitude: lon } = pos.coords;
      let city = '';
      try {
        const [place] = await Location.reverseGeocodeAsync({ latitude: lat, longitude: lon });
        city = place?.city || place?.subregion || place?.region || '';
      } catch {
        // reverse geocoding isn't available on every platform
      }
      onPick({ city: city || `${lat.toFixed(2)}, ${lon.toFixed(2)}`, lat, lon });
    } catch {
      setError(t.errors.unknown);
    } finally {
      setLocating(false);
    }
  }

  return (
    <View style={{ gap: space.md }}>
      <Button label={t.profile.useLocation} kind="secondary" onPress={useMyLocation} loading={locating} />
      <Field label={t.profile.searchCity} value={q} onChangeText={setQ} autoCorrect={false} returnKeyType="search" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {(q.trim().length < 2 ? [] : results).map((c) => (
        <Pressable
          key={`${c.lat},${c.lon}`}
          accessibilityRole="button"
          onPress={() => {
            tap();
            onPick({ city: c.name || c.label, lat: c.lat, lon: c.lon });
          }}
          style={({ pressed }) => ({
            paddingVertical: space.md,
            borderBottomWidth: 1,
            borderColor: p.line,
            opacity: pressed ? 0.7 : 1,
          })}
        >
          <T variant="bodyStrong">{c.name}</T>
          <T variant="small" color="muted">
            {c.label}
          </T>
        </Pressable>
      ))}
    </View>
  );
}
