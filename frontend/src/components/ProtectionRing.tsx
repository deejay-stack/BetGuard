import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import {
  ShieldCheck,
  ShieldOff,
  ShieldAlert,
  LoaderCircle,
} from 'lucide-react-native';
import { useTheme } from '../state/ThemeContext';
import type { Snapshot } from '../state/types';

export function ProtectionRing({
  state,
  blockedEvent,
}: {
  state?: Snapshot['state'];
  blockedEvent?: number;
}) {
  const { colors, reducedMotion } = useTheme();
  const pulse = useRef(new Animated.Value(0)).current;
  const alert = useRef(new Animated.Value(0)).current;
  const previous = useRef(blockedEvent);
  const active = state === 'active';
  const transitioning = state === 'starting' || state === 'stopping';
  const color = active
    ? colors.protected
    : state === 'degraded' || state === 'interrupted'
    ? colors.warning
    : state === 'failed'
    ? colors.danger
    : transitioning
    ? colors.primary
    : colors.inactive;
  const Icon = active
    ? ShieldCheck
    : transitioning
    ? LoaderCircle
    : state === 'off'
    ? ShieldOff
    : ShieldAlert;
  useEffect(() => {
    pulse.setValue(0);
    if (reducedMotion || (!active && !transitioning)) return;
    const animation = Animated.sequence([
      Animated.timing(pulse, {
        toValue: 1,
        duration: 1800,
        useNativeDriver: true,
      }),
      Animated.timing(pulse, {
        toValue: 0,
        duration: 1800,
        useNativeDriver: true,
      }),
    ]);
    animation.start();
    return () => animation.stop();
  }, [active, transitioning, reducedMotion, pulse]);
  useEffect(() => {
    const changed =
      previous.current !== undefined &&
      blockedEvent !== undefined &&
      blockedEvent > previous.current;
    previous.current = blockedEvent;
    if (!changed || !blockedEvent || !active || reducedMotion) return;
    const animation = Animated.sequence([
      Animated.timing(alert, {
        toValue: 0.65,
        duration: 160,
        useNativeDriver: true,
      }),
      Animated.timing(alert, {
        toValue: 0,
        duration: 900,
        useNativeDriver: true,
      }),
    ]);
    animation.start();
    return () => {
      animation.stop();
      alert.setValue(0);
    };
  }, [blockedEvent, active, reducedMotion, alert]);
  return (
    <View
      style={local.container}
      accessible={false}
      importantForAccessibility="no-hide-descendants"
    >
      <Animated.View
        style={[
          local.glow,
          {
            backgroundColor: color,
            opacity: pulse.interpolate({
              inputRange: [0, 1],
              outputRange: [0.04, 0.11],
            }),
            transform: [
              {
                scale: pulse.interpolate({
                  inputRange: [0, 1],
                  outputRange: [1, 1.06],
                }),
              },
            ],
          },
        ]}
      />
      <View style={[local.outer, { borderColor: colors.border }]}>
        <View
          style={[
            local.ring,
            { borderColor: color, backgroundColor: colors.surface },
          ]}
        >
          <Icon size={64} color={color} strokeWidth={1.5} />
        </View>
      </View>
      <Animated.View
        style={[
          local.alert,
          { backgroundColor: colors.blocked, opacity: alert },
        ]}
      />
    </View>
  );
}
const local = StyleSheet.create({
  container: {
    width: 176,
    height: 176,
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
  },
  glow: { position: 'absolute', width: 176, height: 176, borderRadius: 88 },
  outer: {
    width: 152,
    height: 152,
    borderWidth: 1,
    borderRadius: 76,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ring: {
    width: 132,
    height: 132,
    borderRadius: 66,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  alert: { position: 'absolute', width: 132, height: 132, borderRadius: 66 },
});
