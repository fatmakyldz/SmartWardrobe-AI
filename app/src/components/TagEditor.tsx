import { View } from 'react-native';

import { CATEGORIES, COLORS, PATTERNS, SEASONS, SWATCH, Tags } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { space } from '@/lib/theme';

import { Chip, Field, Stepper, T } from './ui';

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: space.sm }}>
      <T variant="smallStrong">{label}</T>
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

export function TagEditor({ value, onChange }: { value: Tags; onChange: (v: Tags) => void }) {
  const { t } = useI18n();
  const set = <K extends keyof Tags>(k: K, v: Tags[K]) => onChange({ ...value, [k]: v });

  return (
    <View style={{ gap: space.xl }}>
      <Field label={t.item.name} value={value.name} onChangeText={(v) => set('name', v)} maxLength={120} />

      <Group label={t.item.category}>
        <Wrap>
          {CATEGORIES.map((c) => (
            <Chip key={c} label={t.categories[c]} selected={value.category === c} onPress={() => set('category', c)} />
          ))}
        </Wrap>
      </Group>

      <Group label={t.item.colors}>
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

      <Group label={t.item.pattern}>
        <Wrap>
          {PATTERNS.map((c) => (
            <Chip key={c} label={t.patterns[c]} selected={value.pattern === c} onPress={() => set('pattern', c)} />
          ))}
        </Wrap>
      </Group>

      <Group label={t.item.warmth}>
        <Stepper value={value.warmth} labels={t.item.warmthScale} onChange={(v) => set('warmth', v)} />
      </Group>

      <Group label={t.item.formality}>
        <Stepper value={value.formality} labels={t.item.formalityScale} onChange={(v) => set('formality', v)} />
      </Group>

      <Group label={t.item.seasons}>
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
