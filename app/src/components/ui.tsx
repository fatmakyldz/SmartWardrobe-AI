import * as Haptics from 'expo-haptics';
import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  PressableProps,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { font, radius, space, type, usePalette } from '@/lib/theme';

export function tap() {
  if (Platform.OS !== 'web') void Haptics.selectionAsync();
}

export function Screen({
  children,
  scroll = true,
  padded = true,
  edges = ['top'],
}: {
  children: ReactNode;
  scroll?: boolean;
  padded?: boolean;
  edges?: ('top' | 'bottom')[];
}) {
  const p = usePalette();
  const inner = padded ? { paddingHorizontal: space.xl, paddingBottom: space.xxxl } : undefined;
  return (
    <SafeAreaView edges={edges} style={{ flex: 1, backgroundColor: p.bg }}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={[inner, styles.maxWidth]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[{ flex: 1 }, inner, styles.maxWidth]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

export function T({
  children,
  variant = 'body',
  color,
  style,
  ...rest
}: {
  children: ReactNode;
  variant?: keyof typeof type;
  color?: 'ink' | 'muted' | 'inkSoft' | 'danger' | 'onInk';
  style?: StyleProp<TextStyle>;
  numberOfLines?: number;
  accessibilityRole?: 'header';
}) {
  const p = usePalette();
  return (
    <Text style={[type[variant], { color: p[color ?? 'ink'] }, style]} {...rest}>
      {children}
    </Text>
  );
}

type ButtonProps = Omit<PressableProps, 'style' | 'children'> & {
  label: string;
  kind?: 'primary' | 'secondary' | 'ghost' | 'danger';
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
};

export function Button({ label, kind = 'primary', loading, disabled, style, onPress, ...rest }: ButtonProps) {
  const p = usePalette();
  const bg = { primary: p.ink, secondary: p.surface, ghost: 'transparent', danger: 'transparent' }[kind];
  const fg = { primary: p.onInk, secondary: p.ink, ghost: p.ink, danger: p.danger }[kind];
  const border = kind === 'secondary' ? p.line : kind === 'danger' ? p.danger : 'transparent';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!loading, busy: !!loading }}
      disabled={disabled || loading}
      onPress={(e) => {
        tap();
        onPress?.(e);
      }}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, borderColor: border, opacity: disabled ? 0.45 : pressed ? 0.8 : 1 },
        style,
      ]}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={[type.bodyStrong, { color: fg, fontFamily: font.semibold }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  swatch,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  swatch?: string;
}) {
  const p = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      onPress={() => {
        tap();
        onPress?.();
      }}
      style={({ pressed }) => [
        styles.chip,
        {
          backgroundColor: selected ? p.tape : p.surface,
          borderColor: selected ? p.tape : p.line,
          opacity: pressed ? 0.8 : 1,
        },
      ]}
    >
      {swatch ? <Swatch color={swatch} size={14} /> : null}
      <Text style={[type.smallStrong, { color: selected ? p.tapeInk : p.ink }]}>{label}</Text>
    </Pressable>
  );
}

export function Swatch({ color, size = 18 }: { color: string; size?: number }) {
  const p = usePalette();
  if (color === 'conic') {
    return (
      <View style={{ width: size, height: size, borderRadius: size / 2, overflow: 'hidden', flexDirection: 'row' }}>
        {['#c0392b', '#e9c84a', '#3f7a4f', '#4f6f99'].map((c) => (
          <View key={c} style={{ flex: 1, backgroundColor: c }} />
        ))}
      </View>
    );
  }
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: p.muted,
      }}
    />
  );
}

export function Field({ label, hint, error, ...props }: TextInputProps & { label: string; hint?: string; error?: string }) {
  const p = usePalette();
  return (
    <View style={{ gap: space.xs }}>
      <T variant="smallStrong">{label}</T>
      <TextInput
        placeholderTextColor={p.muted}
        style={[
          type.body,
          styles.input,
          { backgroundColor: p.surface, borderColor: error ? p.danger : p.line, color: p.ink },
        ]}
        {...props}
      />
      {error ? (
        <T variant="small" color="danger">
          {error}
        </T>
      ) : hint ? (
        <T variant="small" color="muted">
          {hint}
        </T>
      ) : null}
    </View>
  );
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' }) {
  const p = usePalette();
  return (
    <View
      accessibilityRole={tone === 'error' ? 'alert' : undefined}
      style={[
        styles.notice,
        { backgroundColor: tone === 'error' ? 'transparent' : p.surfaceAlt, borderColor: tone === 'error' ? p.danger : p.surfaceAlt },
      ]}
    >
      <T variant="small" color={tone === 'error' ? 'danger' : 'inkSoft'}>
        {children}
      </T>
    </View>
  );
}

export function Stepper({
  value,
  labels,
  onChange,
}: {
  value: number;
  labels: string[];
  onChange: (v: number) => void;
}) {
  const p = usePalette();
  return (
    <View style={{ gap: space.sm }}>
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {labels.map((l, i) => {
          const on = i + 1 <= value;
          return (
            <Pressable
              key={l}
              accessibilityRole="adjustable"
              accessibilityLabel={l}
              accessibilityState={{ selected: i + 1 === value }}
              onPress={() => {
                tap();
                onChange(i + 1);
              }}
              style={{ flex: 1, height: 28, borderRadius: radius.sm, backgroundColor: on ? p.ink : p.surfaceAlt }}
            />
          );
        })}
      </View>
      <T variant="small" color="muted">
        {labels[value - 1]}
      </T>
    </View>
  );
}

const styles = StyleSheet.create({
  maxWidth: { width: '100%', maxWidth: 720, alignSelf: 'center' },
  button: {
    minHeight: 52,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    minHeight: 36,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  input: {
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    paddingVertical: 12,
    minHeight: 50,
  },
  notice: { padding: space.lg, borderRadius: radius.md, borderWidth: 1 },
});
