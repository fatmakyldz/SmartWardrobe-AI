import { View } from 'react-native';

import { CATEGORIES, COLORS, PATTERNS, SEASONS, SWATCH, Tags } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { space, usePalette } from '@/lib/theme';

import { Chip, Field, Stepper, T } from './ui';

function Group({ label, children, check }: { label: string; children: React.ReactNode; check?: boolean }) {
  const { t } = useI18n();
  const p = usePalette();
  return (
    <View style={check ? { gap: space.sm, borderLeftWidth: 3, borderLeftColor: p.tape, paddingLeft: space.md } : { gap: space.sm }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
        <T variant="smallStrong">{label}</T>
        {check ? (
          <T variant="tiny" style={{ color: p.tapeInk, backgroundColor: p.tape, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 }}>
            {t.add.check}
          </T>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function Wrap({ children }: { children: React.ReactNode }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>{children}</View>;
}

function toggle(list: string[], value: string, max: number): string[] {
  if (list.includes(value)) return list.filter((v) => v !== value);
  return list.length >= max ? [...list.slice(1), value] : [...list, value];
}

/** `uncertain`: the fields /items/analyze flagged; they get a "worth a check" mark so the user looks there first. */
export function TagEditor({ value, onChange, uncertain = [] }: { value: Tags; onChange: (v: Tags) => void; uncertain?: (keyof Tags)[] }) {
  const { t } = useI18n();
  const set = <K extends keyof Tags>(k: K, v: Tags[K]) => onChange({ ...value, [k]: v });
  const check = (k: keyof Tags) => uncertain.includes(k);

  return (
    <View style={{ gap: space.xl }}>
      <Field label={t.item.name} value={value.name} onChangeText={(v) => set('name', v)} maxLength={120} />

      <Group label={t.item.category} check={check('category') || check('subcategory')}>
        <Wrap>
          {CATEGORIES.map((c) => (
            <Chip key={c} label={t.categories[c]} selected={value.category === c} onPress={() => set('category', c)} />
          ))}
        </Wrap>
      </Group>

      <Group label={t.item.colors} check={check('colors')}>
        <Wrap>
          {COLORS.map((c) => (
            <Chip
              key={c}
              label={t.colors[c]}
              swatch={SWATCH[c]}
              selected={value.colors.includes(c)}
              onPress={() => set('colors', toggle(value.colors, c, 3))}
            />
          ))}
        </Wrap>
      </Group>

      <Group label={t.item.pattern} check={check('pattern')}>
        <Wrap>
          {PATTERNS.map((c) => (
            <Chip key={c} label={t.patterns[c]} selected={value.pattern === c} onPress={() => set('pattern', c)} />
          ))}
        </Wrap>
      </Group>

      <Group label={t.item.warmth} check={check('warmth')}>
        <Stepper value={value.warmth} labels={t.item.warmthScale} onChange={(v) => set('warmth', v)} />
      </Group>

      <Group label={t.item.formality} check={check('formality')}>
        <Stepper value={value.formality} labels={t.item.formalityScale} onChange={(v) => set('formality', v)} />
      </Group>

      <Group label={t.item.seasons} check={check('seasons')}>
        <Wrap>
          {SEASONS.map((c) => (
            <Chip
              key={c}
              label={t.seasons[c]}
              selected={value.seasons.includes(c)}
              onPress={() => set('seasons', toggle(value.seasons, c, 4))}
            />
          ))}
        </Wrap>
      </Group>
    </View>
  );
}
