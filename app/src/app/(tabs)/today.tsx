import { useMutation, useQuery } from '@tanstack/react-query';
import { router, useIsFocused } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, useWindowDimensions, View } from 'react-native';

import { CityPicker } from '@/components/CityPicker';
import { Button, Chip, Field, Notice, Screen, T, tap } from '@/components/ui';
import { OutfitBoard } from '@/components/wardrobe';
import { api, Gap, Intent, Item, Occasion, OCCASIONS, Outfit } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useErrorText } from '@/lib/errors';
import { skyKey, useI18n } from '@/lib/i18n';
import { useAnalysis, useEntitlements, useFeedback, useHasFeature, useItems, useLatestIntent, useLatestOutfits, useOutfits, useSuggest, useWorn } from '@/lib/queries';
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
  const ent = useEntitlements(!!user).data;
  const canEdit = useHasFeature('user_outfits') === true;
  const intent = useLatestIntent().data;

  const cats = new Set((items.data ?? []).map((i) => i.category));
  const ready = cats.has('dress') || (cats.has('top') && cats.has('bottom'));
  // Progressive wardrobe: one nudge at a time, deterministic, no AI request. Demo wardrobes are complete.
  const analysis = useAnalysis(!!user && !user.is_demo && ready);
  // Same condition as `enabled`: the query key is shared with the analysis screen, so a demo user could
  // otherwise see cached gaps here. Below 'ready' the incomplete notice says it all.
  const nudge = ready && user && !user.is_demo ? pickNudge(analysis.data?.gaps ?? [], items.data ?? []) : null;

  // The first outfit comes without a tap (§10 step 2, and the first-pieces flow): once per account,
  // only while it has no outfit at all, so coming back to the tab doesn't spend another request.
  // Only while this tab is on screen: the tabs stay mounted under the add-item modal, and a piece
  // saved there must not spend a request from here before the user is done.
  const focused = useIsFocused();
  const history = useOutfits(false, !!user && ready && focused);
  const autoFor = useRef<string | null>(null);
  const [autoShown, setAutoShown] = useState(false);
  useEffect(() => {
    if (!user || !ready || !focused || !history.isSuccess || history.data.length > 0) return;
    if (autoFor.current === user.id || suggest.isPending) return;
    autoFor.current = user.id;
    setAutoShown(true);
    suggest.mutate({ occasion: 'casual', note: '', lang });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, ready, focused, history.isSuccess, history.data?.length]);

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
          <Notice>{resent ? t.today.resent : t.today.verifyBanner(user.email, ent?.after_verify?.max_items ?? 50, ent?.after_verify?.daily_ai_requests ?? 5)}</Notice>
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
            label={parse && note.trim() ? t.today.request : t.today.note}
            placeholder={parse ? t.today.requestPlaceholder : t.today.notePlaceholder}
            value={note}
            onChangeText={(v) => {
              setNote(v);
              if (!v.trim()) setParse(false);
            }}
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
              // With parse on the text goes as `request` (parsed) and stays the note, so history keeps it.
              suggest.mutate(parse && text ? { occasion, note: text, request: text, lang } : { occasion, note: text, lang });
            }}
          />
          {ent ? (
            <T variant="small" color="muted">
              {t.today.quota(ent.usage.requests_left, ent.daily_ai_requests)}
            </T>
          ) : null}
          {intent && intentSummary(intent, t, lang) ? (
            <T variant="small" color="muted">
              {t.today.understood} {intentSummary(intent, t, lang)}
            </T>
          ) : null}
        </View>
      )}

      {nudge ? (
        <View style={{ marginTop: space.xl, padding: space.lg, borderRadius: 16, backgroundColor: p.surface, borderWidth: 1, borderColor: p.line, gap: space.sm }}>
          <T variant="small" color="muted">
            {t.today.nudgeTitle}
          </T>
          <T variant="body">{nudgeText(nudge, t, lang)}</T>
          {nudge.gap.category ? (
            <Button
              label={t.today.nudgeAdd(t.categories[nudge.gap.category])}
              kind="secondary"
              onPress={() => router.push({ pathname: '/item/new', params: { category: nudge.gap.category! } })}
            />
          ) : null}
        </View>
      ) : null}

      <View style={{ gap: space.xxl, marginTop: space.xxl }}>
        {autoShown && outfits.length ? <Notice>{user?.is_demo ? t.today.firstDemo : t.today.firstAuto}</Notice> : null}
        {worn.isError ? <Notice tone="error">{errorText(worn.error)}</Notice> : null}
        {outfits.map((o) => (
          <OutfitBoard
            key={o.id}
            outfit={o}
            width={boardWidth}
            onRate={(r) => rate(o, r)}
            onOpenItem={(item) => router.push({ pathname: '/item/[id]', params: { id: item.id } })}
            onWorn={() => {
              tap();
              worn.mutate(o.id);
            }}
            onEdit={canEdit ? () => router.push({ pathname: '/outfit/[id]', params: { id: o.id } }) : undefined}
          />
        ))}
      </View>
    </Screen>
  );
}

type Nudge = { gap: Gap; piece: Item | null };

// Which gap to show: what blocks outfits first, then the one tied to a specific piece (the most
// personal), then the rest. One card, so adding a piece changes it rather than stacking.
const NUDGE_ORDER: Gap['code'][] = ['missing_category', 'occasion_uncovered', 'few_partners', 'orphan_items', 'season_uncovered', 'few_shoes', 'low_neutrals'];
const EVERYDAY = new Set(['casual', 'work']);

// Everyday occasions first; a missing black-tie top is not the next thing a 3-piece wardrobe needs.
function rank(g: Gap): number {
  const base = NUDGE_ORDER.indexOf(g.code);
  return g.code === 'occasion_uncovered' && !EVERYDAY.has(g.occasion ?? '') ? NUDGE_ORDER.indexOf('season_uncovered') + 0.5 : base;
}

function pickNudge(gaps: Gap[], items: Item[]): Nudge | null {
  const sorted = [...gaps].sort((a, b) => rank(a) - rank(b));
  for (const gap of sorted) {
    if (!NUDGE_ORDER.includes(gap.code)) continue;
    const piece = gap.item_ids.length ? (items.find((i) => i.id === gap.item_ids[0]) ?? null) : null;
    if (gap.item_ids.length && !piece) continue; // the piece isn't in the list yet (stale after a delete)
    return { gap, piece };
  }
  return null;
}

function nudgeText(n: Nudge, t: ReturnType<typeof useI18n>['t'], lang: string): string {
  const category = n.gap.category ? t.categories[n.gap.category] : '';
  const occasion = n.gap.occasion ? t.occasions[n.gap.occasion].toLocaleLowerCase(lang) : '';
  const piece = n.piece ? n.piece.name || t.categories[n.piece.category] : '';
  return t.today.nudge(n.gap.code, category, occasion, piece);
}

/** "work · no dress · with navy · with a layer" — the parsed request in the user's words. */
function intentSummary(i: Intent, t: ReturnType<typeof useI18n>['t'], lang: string): string {
  const parts: string[] = [];
  if (i.occasion) parts.push(t.occasions[i.occasion]);
  const lc = (x: string) => x.toLocaleLowerCase(lang); // Turkish dotted İ: 'İş' -> 'iş'
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
