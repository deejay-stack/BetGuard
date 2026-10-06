import React, { useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AlertCircle, X, type LucideIcon } from 'lucide-react-native';
import { useTheme } from '../state/ThemeContext';
import type { ThemeColors } from '../theme';
import { useBetGuard } from '../state/BetGuardContext';
import { BrandLogo } from './BrandLogo';

export function Page({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  const { colors, styles } = useTheme();
  const local = makeLocal(colors);
  const {
    error,
    feedback,
    dismissError,
    dismissFeedback,
    available,
    refresh,
    busy,
  } = useBetGuard();
  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
      >
        <View style={[styles.spread, styles.wrap]}>
          <View style={styles.row} accessible accessibilityLabel="BetGuard">
            <BrandLogo size={32} />
            <Text style={local.wordmark}>BetGuard</Text>
          </View>
          {__DEV__ && <Badge text="USB DEVELOPMENT" />}
        </View>
        <View style={local.titleGroup}>
          <Text accessibilityRole="header" style={styles.title}>
            {title}
          </Text>
          <Text style={styles.body}>{subtitle}</Text>
        </View>
        {!available && (
          <Notice text="Native protection is unavailable in this build. Use the Android app to manage and apply rules." />
        )}
        {error && (
          <View>
            <Notice text={error} tone="error" />
            {available && (
              <Button
                title="Retry status"
                secondary
                disabled={busy}
                onPress={() => {
                  void refresh();
                }}
              />
            )}
            <Button title="Dismiss error" secondary onPress={dismissError} />
          </View>
        )}
        {feedback && (
          <View style={[styles.card, styles.row]}>
            <Text
              accessibilityLiveRegion="polite"
              numberOfLines={2}
              style={[styles.body, styles.flex]}
            >
              {feedback.split('. ')[0]}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Dismiss rule feedback"
              onPress={dismissFeedback}
              style={local.dismiss}
            >
              <X size={20} color={colors.textMuted} />
            </Pressable>
          </View>
        )}
        {children}
        <Text style={local.footer}>Your rules. Your choice.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
export function Card({ children }: { children: React.ReactNode }) {
  const { styles } = useTheme();
  return <View style={styles.card}>{children}</View>;
}
export function Button({
  title,
  onPress,
  disabled,
  busy,
  secondary,
  icon: Icon,
  accessibilityLabel,
  selected,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  secondary?: boolean;
  icon?: LucideIcon;
  accessibilityLabel?: string;
  selected?: boolean;
}) {
  const { colors, reducedMotion } = useTheme();
  const local = makeLocal(colors);
  const scale = useRef(new Animated.Value(1)).current;
  const blocked = !!disabled || !!busy;
  const foreground = blocked
    ? colors.onDisabled
    : secondary
    ? colors.primary
    : colors.onPrimary;
  useEffect(() => {
    if (reducedMotion || blocked) {
      scale.stopAnimation();
      scale.setValue(1);
    }
    return () => scale.stopAnimation();
  }, [reducedMotion, blocked, scale]);
  function press(value: number) {
    if (reducedMotion) {
      return;
    }
    Animated.timing(scale, {
      toValue: value,
      duration: 90,
      useNativeDriver: true,
    }).start();
  }
  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? title}
        accessibilityState={{ disabled: blocked, busy: !!busy, selected }}
        disabled={blocked}
        onPress={onPress}
        onPressIn={() => press(0.98)}
        onPressOut={() => press(1)}
        style={({ pressed }) => [
          local.button,
          secondary && local.secondary,
          blocked && local.disabled,
          pressed && local.pressed,
        ]}
      >
        {busy ? (
          <ActivityIndicator color={foreground} size="small" />
        ) : Icon ? (
          <Icon size={20} color={foreground} accessible={false} />
        ) : null}
        <Text style={[local.buttonText, { color: foreground }]}>{title}</Text>
      </Pressable>
    </Animated.View>
  );
}
type Tone = 'primary' | 'success' | 'warning' | 'error' | 'inactive';
export function Badge({
  text,
  tone = 'primary',
}: {
  text: string;
  tone?: Tone;
}) {
  const { colors } = useTheme();
  const local = makeLocal(colors);
  return (
    <View style={[local.badge, { backgroundColor: colors[`${tone}Soft`] }]}>
      <Text style={[local.badgeText, { color: colors[tone] }]}>{text}</Text>
    </View>
  );
}
export function Notice({
  text,
  tone = 'warning',
}: {
  text: string;
  tone?: 'warning' | 'error';
}) {
  const { colors, styles } = useTheme();
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[
        makeLocal(colors).notice,
        { backgroundColor: colors[`${tone}Soft`] },
      ]}
    >
      <AlertCircle size={18} color={colors[tone]} accessible={false} />
      <Text style={[styles.small, styles.flex, { color: colors[tone] }]}>
        {text}
      </Text>
    </View>
  );
}
export function Empty({ title, body }: { title: string; body: string }) {
  const { colors, styles } = useTheme();
  return (
    <View style={makeLocal(colors).empty}>
      <Text style={styles.heading}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
    </View>
  );
}
export function Loading() {
  const { colors, styles } = useTheme();
  return (
    <View
      style={styles.row}
      accessible
      accessibilityLabel="Loading saved rules and status"
      accessibilityState={{ busy: true }}
    >
      <BrandLogo size={30} />
      <ActivityIndicator color={colors.primary} />
      <Text style={styles.small}>Reading saved data...</Text>
    </View>
  );
}
const makeLocal = (colors: ThemeColors) =>
  StyleSheet.create({
    dismiss: {
      minWidth: 48,
      minHeight: 48,
      alignItems: 'center',
      justifyContent: 'center',
    },
    wordmark: {
      fontSize: 20,
      fontWeight: '700',
      color: colors.text,
      letterSpacing: -0.6,
    },
    titleGroup: {
      gap: 8,
      marginTop: 4,
      marginBottom: 4,
    },
    button: {
      minHeight: 52,
      backgroundColor: colors.primary,
      paddingHorizontal: 17,
      paddingVertical: 13,
      borderRadius: 16,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
    },
    secondary: { backgroundColor: colors.primarySoft },
    buttonText: {
      fontSize: 14,
      fontWeight: '700',
      flexShrink: 1,
      textAlign: 'center',
    },
    disabled: { backgroundColor: colors.disabled },
    pressed: { opacity: 0.75 },
    badge: {
      paddingHorizontal: 9,
      paddingVertical: 5,
      borderRadius: 100,
      alignSelf: 'flex-start',
      flexShrink: 1,
    },
    badgeText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
    notice: {
      padding: 14,
      borderRadius: 12,
      flexDirection: 'row',
      gap: 10,
      alignItems: 'flex-start',
    },
    empty: { paddingVertical: 18, gap: 8 },
    footer: {
      fontSize: 12,
      textAlign: 'center',
      color: colors.textMuted,
      marginTop: 8,
    },
  });
