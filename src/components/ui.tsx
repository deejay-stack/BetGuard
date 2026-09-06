import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AlertCircle, Shield } from 'lucide-react-native';
import { colors, styles } from '../theme';
import { useBetGuard } from '../state/BetGuardContext';

export function Page({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  const { error, dismissError, available } = useBetGuard();
  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={styles.page}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.spread}>
          <View style={styles.row}>
            <View style={local.brand}>
              <Shield color={colors.blue} size={22} />
            </View>
            <Text style={local.wordmark}>BetGuard</Text>
          </View>
          <Badge text="PROTOTYPE" />
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
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Dismiss error"
            onPress={dismissError}
          >
            <Notice text={error} tone="red" />
          </Pressable>
        )}
        {children}
        <Text style={local.footer}>Your rules. Your choice.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
export function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}
export function Button({
  title,
  onPress,
  disabled,
  busy,
  secondary,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!busy, busy: !!busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        local.button,
        secondary && local.secondary,
        (disabled || busy) && local.disabled,
        pressed && local.pressed,
      ]}
    >
      {busy && (
        <ActivityIndicator
          color={secondary ? colors.blue : colors.white}
          size="small"
        />
      )}
      <Text style={[local.buttonText, secondary && local.secondaryText]}>
        {title}
      </Text>
    </Pressable>
  );
}
export function Badge({
  text,
  tone = 'blue',
}: {
  text: string;
  tone?: 'blue' | 'green' | 'amber' | 'red';
}) {
  return (
    <View style={[local.badge, { backgroundColor: colors[`${tone}Soft`] }]}>
      <Text style={[local.badgeText, { color: colors[tone] }]}>{text}</Text>
    </View>
  );
}
export function Notice({
  text,
  tone = 'amber',
}: {
  text: string;
  tone?: 'amber' | 'red';
}) {
  return (
    <View style={[local.notice, { backgroundColor: colors[`${tone}Soft`] }]}>
      <AlertCircle size={18} color={colors[tone]} />
      <Text style={[styles.small, styles.flex, { color: colors[tone] }]}>
        {text}
      </Text>
    </View>
  );
}
export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <View style={local.empty}>
      <Text style={styles.heading}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
    </View>
  );
}
export function Loading() {
  return (
    <ActivityIndicator
      accessibilityLabel="Loading saved rules"
      color={colors.blue}
    />
  );
}
const local = StyleSheet.create({
  brand: { backgroundColor: colors.blueSoft, padding: 9, borderRadius: 12 },
  wordmark: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.ink,
    letterSpacing: -0.6,
  },
  titleGroup: { gap: 6, marginTop: 10 },
  button: {
    minHeight: 48,
    backgroundColor: colors.blue,
    paddingHorizontal: 17,
    paddingVertical: 13,
    borderRadius: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  secondary: { backgroundColor: colors.blueSoft },
  buttonText: { fontSize: 14, fontWeight: '700', color: colors.white },
  secondaryText: { color: colors.blue },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.8 },
  badge: {
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 7,
    alignSelf: 'flex-start',
    flexShrink: 1,
  },
  badgeText: { fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },
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
    color: colors.muted,
    marginTop: 8,
  },
});
