import { useMutation, useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, useWindowDimensions, View } from 'react-native';

import { CityPicker } from '@/components/CityPicker';
import { Button, Chip, Field, Notice, Screen, T, tap } from '@/components/ui';
import { OutfitBoard } from '@/components/wardrobe';
import { api, Intent, Occasion, OCCASIONS, Outfit } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { skyKey, useI18n } from '@/lib/i18n';
import { useFeedback, useItems, useLatestIntent, useLatestOutfits, useOutfits, useSuggest, useWorn } from '@/lib/queries';
import { space, usePalette } from '@/lib/theme';

export default function Today() {
  const p = usePalette();
  const { t, lang } = useI18n();
  const { user, setUser } = useAuth();
  const errorText = useErrorText();
  const { width } = useWindowDimensions();
  const boardWidth = Math.min(width, 720) - space.xl * 2;

  const [occasion, setOccasion] = useState<Occasion>('casual');
  const [note, setNote] = useState('');
  const [parse, setParse] = useState(false); // send the text as `request` (parsed, one extra AI request)
  const [pickingCity, setPickingCity] = useState(false);

  const items = useItems();
  const outfits = useLatestOutfits().data;
  const hasLocation = user?.lat != null && user?.lon != null;
  const weather = useQuery({
    queryKey: ['weather', user?.lat, user?.lon],
    queryFn: () => api.weather(user!.lat!, user!.lon!),
    enabled: hasLocation,
    staleTime: 15 * 60_000,
  });

  const suggest = useSuggest();
  const feedback = useFeedback();
  const worn = useWorn();
  const intent = useLatestIntent().data;

  const cats = new Set((items.data ?? []).map((i) => i.category));
  const ready = cats.has('dress') || (cats.has('top') && cats.has('bottom'));

  // A demo account's first visit gets a suggestion without a tap (§10 step 2): once per account, and
  // only while it has no outfit at all, so coming back to the tab doesn't spend another request.
  const history = useOutfits(false, !!user?.is_demo);
  const autoFor = useRef<string | null>(null);
  const [autoShown, setAutoShown] = useState(false);
  useEffect(() => {
    if (!user?.is_demo || !ready || !history.isSuccess || history.data.length > 0) return;
    if (autoFor.current === user.id || suggest.isPending) return;
    autoFor.current = user.id;
    setAutoShown(true);
    suggest.mutate({ occasion: 'casual', note: '', lang });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.is_demo, user?.id, ready, history.isSuccess, history.data?.length]);

  async function pickCity(c: { city: string; lat: number; lon: number }) {
    setPickingCity(false);
    setUser(await api.updateMe(c));
  }

  function rate(o: Outfit, r: -1 | 1) {
    feedback.mutate({ id: o.id, rating: o.rating === r ? 0 : r });
  }

  const [resent, setResent] = useState(false);
  const resend = useMutation({ mutationFn: api.resendVerification, onSuccess: () => setResent(true) });
  const unverified = !!user && !user.is_demo && !user.email_verified_at;

  const w = weather.data;
  return (
    <Screen>
      {unverified ? (
        <View style={{ marginTop: space.lg, gap: space.sm }}>
          <Notice>{resent ? t.today.resent : t.today.verifyBanner(user.email)}</Notice>
          {resend.isError ? <Notice tone="error">{errorText(resend.error)}</Notice> : null}
          {!resent ? (
            <Button label={t.today.resend} kind="secondary" loading={resend.isPending} onPress={() => resend.mutate()} />
          ) : null}
        </View>
      ) : null}

      {/* The day, as a headline */}
      <View style={{ marginTop: space.xl, marginBottom: space.xl }}>
        {hasLocation && w?.temp != null ? (
          <Pressable accessibilityRole="button" onPress={() => setPickingCity((v) => !v)}>
            <T variant="display" accessibilityRole="header">
              {t.today.weatherLine(user!.city, Math.round(w.temp), t.sky[skyKey(w.code)])}
            </T>
            {w.min != null && w.max != null ? (
              <T variant="body" color="muted" style={{ marginTop: space.sm }}>
                {t.today.range(Math.round(w.min), Math.round(w.max), Math.round(w.rain_chance ?? 0))}
              </T>
            ) : null}
          </Pressable>
        ) : hasLocation && weather.isLoading ? (
          <ActivityIndicator color={p.ink} style={{ alignSelf: 'flex-start' }} />
        ) : (
          <>
            <T variant="display" accessibilityRole="header">
              {t.today.noCity}
            </T>
            {!pickingCity ? (
              <Button label={t.today.setCity} kind="secondary" onPress={() => setPickingCity(true)} style={{ marginTop: space.lg }} />
            ) : null}
            {weather.isError ? (
              <T variant="small" color="muted" style={{ marginTop: space.sm }}>
                {t.errors.weather_unavailable}
              </T>
            ) : null}
          </>
        )}
      </View>

      {pickingCity ? (
        <View style={{ marginBottom: space.xl }}>
          <CityPicker onPick={pickCity} />
        </View>
      ) : null}

      {items.isSuccess && !ready ? (
        <View style={{ gap: space.md }}>
          <Notice>{t.today.incomplete}</Notice>
          <Button label={t.today.addItems} onPress={() => router.push('/item/new')} />
        </View>
      ) : (
        <View style={{ gap: space.lg }}>
          <T variant="heading">{t.today.occasion}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
            {OCCASIONS.map((o) => (
              <Chip key={o} label={t.occasions[o]} selected={occasion === o} onPress={() => setOccasion(o)} />
            ))}
          </View>
          <Field
            label={parse ? t.today.request : t.today.note}
            placeholder={parse ? t.today.requestPlaceholder : t.today.notePlaceholder}
            value={note}
            onChangeText={setNote}
            maxLength={200}
          />
          {note.trim() ? (
            <View style={{ gap: space.xs }}>
              <View style={{ flexDirection: 'row' }}>
                <Chip label={t.today.parseWithAi} selected={parse} onPress={() => setParse((v) => !v)} />
              </View>
              {parse ? (
                <T variant="small" color="muted">
                  {t.today.parseHint}
                </T>
              ) : null}
            </View>
          ) : null}
          {suggest.isError ? <Notice tone="error">{errorText(suggest.error)}</Notice> : null}
          <Button
            label={suggest.isPending ? t.today.suggesting : outfits.length ? t.today.again : t.today.suggest}
            loading={suggest.isPending}
            onPress={() => {
              tap();
              const text = note.trim();
              setAutoShown(false);
              suggest.mutate(parse && text ? { occasion, note: '', request: text, lang } : { occasion, note: text, lang });
            }}
          />
          {intent ? (
            <T variant="small" color="muted">
              {t.today.understood} {intentSummary(intent, t)}
            </T>
          ) : null}
        </View>
      )}

      <View style={{ gap: space.xxl, marginTop: space.xxl }}>
        {autoShown && outfits.length ? <Notice>{t.today.firstDemo}</Notice> : null}
        {outfits.map((o) => (
          <OutfitBoard
            key={o.id}
            outfit={o}
            width={boardWidth}
            onRate={(r) => rate(o, r)}
            onOpenItem={(item) => router.push({ pathname: '/item/[id]', params: { id: item.id } })}
            onWorn={() => worn.mutate(o.id)}
            onEdit={user?.is_demo ? undefined : () => router.push({ pathname: '/outfit/[id]', params: { id: o.id } })}
          />
        ))}
      </View>
    </Screen>
  );
}

/** "work · no dress · with navy · with a layer" — the parsed request in the user's words. */
function intentSummary(i: Intent, t: ReturnType<typeof useI18n>['t']): string {
  const parts: string[] = [];
  if (i.occasion) parts.push(t.occasions[i.occasion]);
  const lc = (x: string) => x.toLowerCase();
  const inc = [...i.include_categories.map((c) => lc(t.categories[c])), ...i.include_colors.map((c) => lc(t.colors[c as keyof typeof t.colors] ?? c))];
  if (inc.length) parts.push(t.today.with(inc.join(', ')));
  const avoid = [
    ...i.avoid_categories.map((c) => lc(t.categories[c])),
    ...i.avoid_colors.map((c) => lc(t.colors[c as keyof typeof t.colors] ?? c)),
    ...i.avoid_patterns.map((x) => lc(t.patterns[x as keyof typeof t.patterns] ?? x)),
  ];
  if (avoid.length) parts.push(t.today.avoid(avoid.join(', ')));
  if (i.wants_outerwear === true) parts.push(t.today.outerwearYes);
  if (i.wants_outerwear === false) parts.push(t.today.outerwearNo);
  return parts.length ? parts.join(' · ') : i.brief;
}
