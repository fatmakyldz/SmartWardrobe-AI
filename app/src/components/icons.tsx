import Svg, { Circle, Path } from 'react-native-svg';

type P = { color: string; size?: number };
const base = (size: number) => ({ width: size, height: size, viewBox: '0 0 24 24', fill: 'none' as const });

// Hand-drawn line icons, 1.8px stroke, matching the rounded type.
export function TodayIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Circle cx="12" cy="12" r="4" stroke={color} strokeWidth={1.8} />
      <Path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

export function HangerIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Path
        d="M12 7.5a2 2 0 1 1 2-2M12 7.5v1.6L3.4 15.2a1.3 1.3 0 0 0 .8 2.3h15.6a1.3 1.3 0 0 0 .8-2.3L12 9.1"
        stroke={color}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function HeartIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Path
        d="M12 19.5s-7-4.3-7-9.4A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.1c0 5.1-7 9.4-7 9.4Z"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function PersonIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Circle cx="12" cy="8.5" r="3.5" stroke={color} strokeWidth={1.8} />
      <Path d="M5 19.5c1.2-3.3 3.9-5 7-5s5.8 1.7 7 5" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

export function PlusIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Path d="M12 5v14M5 12h14" stroke={color} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}

export function CloseIcon({ color, size = 24 }: P) {
  return (
    <Svg {...base(size)}>
      <Path d="M6 6l12 12M18 6 6 18" stroke={color} strokeWidth={2} strokeLinecap="round" />
    </Svg>
  );
}
