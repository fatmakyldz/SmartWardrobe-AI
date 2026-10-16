import { useColorScheme } from 'react-native';

/*
 * Palette: an atelier, not a café.
 * oyster (ground) · paper (surfaces) · aubergine (ink, primary actions)
 * heather (secondary text) · tape (tailor's-tape yellow: selection and the one accent)
 */
const light = {
  bg: '#ECE8E3',
  surface: '#F8F6F3',
  surfaceAlt: '#E2DDD6',
  ink: '#2A1B26',
  inkSoft: '#4A3A45',
  muted: '#7A6E74',
  line: '#D3CCC4',
  tape: '#E3B23C',
  tapeInk: '#2A1B26',
  onInk: '#F8F6F3',
  danger: '#A8322D',
  board: '#E4DED6',
};

const dark: typeof light = {
  bg: '#19121A',
  surface: '#241B24',
  surfaceAlt: '#2F252F',
  ink: '#F1ECEF',
  inkSoft: '#D6CCD3',
  muted: '#A99BA4',
  line: '#3A2F39',
  tape: '#E8BE52',
  tapeInk: '#19121A',
  onInk: '#19121A',
  danger: '#E2736C',
  board: '#2A212A',
};

export type Palette = typeof light;

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

export const font = {
  light: 'BricolageGrotesque_300Light',
  regular: 'BricolageGrotesque_400Regular',
  medium: 'BricolageGrotesque_500Medium',
  semibold: 'BricolageGrotesque_600SemiBold',
  bold: 'BricolageGrotesque_700Bold',
  heavy: 'BricolageGrotesque_800ExtraBold',
};

// Type scale (modular, ~1.25) — display sizes are tight, body is airy.
export const type = {
  display: { fontFamily: font.heavy, fontSize: 40, lineHeight: 42, letterSpacing: -1.2 },
  title: { fontFamily: font.bold, fontSize: 28, lineHeight: 32, letterSpacing: -0.6 },
  heading: { fontFamily: font.semibold, fontSize: 20, lineHeight: 26, letterSpacing: -0.2 },
  body: { fontFamily: font.regular, fontSize: 16, lineHeight: 24 },
  bodyStrong: { fontFamily: font.medium, fontSize: 16, lineHeight: 24 },
  small: { fontFamily: font.regular, fontSize: 14, lineHeight: 20 },
  smallStrong: { fontFamily: font.semibold, fontSize: 14, lineHeight: 20 },
  tiny: { fontFamily: font.medium, fontSize: 12, lineHeight: 16 },
} as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };
