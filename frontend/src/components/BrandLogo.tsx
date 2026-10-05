import React from 'react';
import Svg, { Path } from 'react-native-svg';
import { useTheme } from '../state/ThemeContext';

// Shield + browser window + a quiet access-stop bar. No classification claim.
export function BrandLogo({
  size = 42,
  color,
  accentColor,
}: {
  size?: number;
  color?: string;
  accentColor?: string;
}) {
  const { colors } = useTheme();
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" accessible={false}>
      <Path
        d="M32 4 L55 13 V31 C55 45 45 55 32 60 C19 55 9 45 9 31 V13 Z"
        fill={color ?? colors.primary}
      />
      <Path
        d="M21 20 H43 Q46 20 46 23 V39 Q46 42 43 42 H21 Q18 42 18 39 V23 Q18 20 21 20 Z M18 27 H46"
        fill="none"
        stroke={colors.onPrimary}
        strokeWidth={3}
        strokeLinejoin="round"
      />
      <Path
        d="M22 23.5 H22.1 M26 23.5 H26.1"
        stroke={colors.onPrimary}
        strokeWidth={1.5}
        strokeLinecap="round"
      />
      <Path
        d="M27 35 H37"
        fill="none"
        stroke={colors.onPrimary}
        strokeWidth={3.5}
        strokeLinecap="round"
      />
      <Path
        d="M24 48 Q28 51 32 53 Q36 51 40 48"
        fill="none"
        stroke={accentColor ?? colors.accent}
        strokeWidth={3}
        strokeLinecap="round"
      />
    </Svg>
  );
}
