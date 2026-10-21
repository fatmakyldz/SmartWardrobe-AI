import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { ReactNode, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';

import { CloseIcon } from '@/components/icons';
import { Chip, Notice, Screen, T } from '@/components/ui';
import {
  api,
  CATEGORIES,
  COLORS,
  Palette,
  PALETTES,
  PATTERNS,
  PRIORITIES,
  Priority,
  STYLES,
  StylePatch,
  StyleProfile,
  SWATCH,
} from '@/lib/api';
import { useErrorText } from '@/lib/errors';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

const AVOIDABLE = [...PATTERNS, ...CATEGORIES] as const;

function toggle<T>(list: readonly T[], x: T): T[] {
  return list.includes(x) ? list.filter((v) => v !== x) : [...list, x];
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={{ gap: space.md }}>
      <T variant="heading">{title}</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>{children}</View>
    </View>
  );
}

/** Explicit preferences (§10 step 6): every chip saves on tap, the taste summary is read-only. */
export default function StyleScreen() {
  const p = usePalette();
  const { t } = useI18n();
  const qc = useQueryClient();
  const errorText = useErrorText();
  const profile = useQuery({ queryKey: ['style'], queryFn: api.style });
  const [saved, setSaved] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useMutation({
    mutationFn: (patch: StylePatch) => api.updateStyle(patch),
    onSuccess: (data) => {
      qc.setQueryData<StyleProfile>(['style'], data);
      setSaved(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setSaved(false), 1500);
    },
  });
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const s = profile.data;

  return (
    <Screen edges={['top', 'bottom']}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t.common.close}
        onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
        style={{ alignSelf: 'flex-start', paddingVertical: space.md }}
        hitSlop={12}
      >
        <CloseIcon color={p.ink} />
      </Pressable>

      <T variant="title" accessibilityRole="header" style={{ marginTop: space.lg }}>
        {t.style.title}
      </T>
      <T variant="body" color="inkSoft" style={{ marginTop: space.sm }}>
        {t.style.intro}
      </T>

      {profile.isError ? (
        <View style={{ marginTop: space.xl }}>
          <Notice tone="error">{errorText(profile.error)}</Notice>
        </View>
      ) : null}
      {!s ? (
        <ActivityIndicator color={p.ink} style={{ alignSelf: 'flex-start', marginTop: space.xl }} />
      ) : (
        <View style={{ gap: space.xxl, marginTop: space.xxl }}>
          <Section title={t.style.styles}>
            {STYLES.map((x) => (
              <Chip
                key={x}
                label={t.styleNames[x]}
                selected={s.answers.q1 === x || s.styles.includes(x)}
                onPress={() => {
                  const primary = s.answers.q1 === x;
                  save.mutate(
                    primary
                      ? { answers: { q1: null }, styles: s.styles.filter((v) => v !== x) }
                      : { styles: toggle(s.styles, x) },
                  );
                }}
              />
            ))}
          </Section>

          <Section title={t.style.palettes}>
            {PALETTES.map((x) => (
              <Chip
                key={x}
                label={t.paletteNames[x]}
                selected={(s.answers.q2 ?? []).includes(x)}
                onPress={() => save.mutate({ answers: { q2: toggle((s.answers.q2 ?? []) as Palette[], x) } })}
              />
            ))}
          </Section>

          <Section title={t.style.priority}>
            {PRIORITIES.map((x) => (
              <Chip
                key={x}
                label={t.priorityNames[x]}
                selected={s.answers.q3 === x}
                onPress={() => save.mutate({ answers: { q3: s.answers.q3 === x ? null : (x as Priority) } })}
              />
            ))}
          </Section>

          <Section title={t.style.liked}>
            {COLORS.map((c) => (
              <Chip
                key={c}
                label={t.colors[c]}
                swatch={SWATCH[c]}
                selected={s.liked_colors.includes(c)}
                onPress={() => save.mutate({ liked_colors: toggle(s.liked_colors, c).slice(0, 8) })}
              />
            ))}
          </Section>

          <Section title={t.style.disliked}>
            {COLORS.map((c) => (
              <Chip
                key={c}
                label={t.colors[c]}
                swatch={SWATCH[c]}
                selected={s.disliked_colors.includes(c)}
                onPress={() => save.mutate({ disliked_colors: toggle(s.disliked_colors, c).slice(0, 8) })}
              />
            ))}
          </Section>

          <Section title={t.style.avoid}>
            {AVOIDABLE.map((x) => (
              <Chip
                key={x}
                label={x in t.patterns ? t.patterns[x as keyof typeof t.patterns] : t.categories[x as keyof typeof t.categories]}
                selected={s.avoid.includes(x)}
                onPress={() => save.mutate({ avoid: toggle(s.avoid, x).slice(0, 8) })}
              />
            ))}
          </Section>

          {s.summary ? (
            <View style={{ gap: space.sm }}>
              <T variant="heading">{t.style.summary}</T>
              <T variant="body" color="inkSoft">
                {s.summary}
              </T>
            </View>
          ) : null}

          {save.isError ? <Notice tone="error">{errorText(save.error)}</Notice> : null}
          {saved ? (
            <T variant="small" color="muted">
              {t.style.saved}
            </T>
          ) : null}
        </View>
      )}
    </Screen>
  );
}
