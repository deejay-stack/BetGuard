import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Alert,
  AppState,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Pause } from 'lucide-react-native';
import { useTheme } from '../state/ThemeContext';

export const HOLD_DURATION = 2500;
export function HoldButton({
  onComplete,
  disabled,
  cancelKey,
  title = 'Hold to pause protection',
  confirmationTitle = 'Pause protection?',
  confirmationMessage = 'Websites will no longer be filtered. Your saved rules will stay on this phone.',
  confirmationAction = 'Pause protection',
}: {
  onComplete: () => void;
  disabled?: boolean;
  cancelKey?: number;
  title?: string;
  confirmationTitle?: string;
  confirmationMessage?: string;
  confirmationAction?: string;
}) {
  const { colors, styles } = useTheme();
  const [progress, setProgress] = useState(0);
  const [screenReader, setScreenReader] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const completed = useRef(false);
  useEffect(() => {
    let live = true;
    let changed = false;
    void AccessibilityInfo.isScreenReaderEnabled()
      .then(value => {
        if (live && !changed) setScreenReader(value);
      })
      .catch(() => {});
    const subscription = AccessibilityInfo.addEventListener(
      'screenReaderChanged',
      value => {
        changed = true;
        setScreenReader(value);
      },
    );
    return () => {
      live = false;
      subscription.remove();
    };
  }, []);
  function cancel() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setProgress(0);
  }
  useEffect(() => {
    cancel();
    const subscription = AppState.addEventListener('change', state => {
      if (state !== 'active') cancel();
    });
    return () => {
      if (timer.current) clearInterval(timer.current);
      subscription.remove();
    };
  }, [disabled, cancelKey]);
  function begin() {
    if (disabled || timer.current) return;
    completed.current = false;
    const began = Date.now();
    timer.current = setInterval(() => {
      const next = Math.min(1, (Date.now() - began) / HOLD_DURATION);
      setProgress(next);
      if (next >= 1) {
        cancel();
        completed.current = true;
        onComplete();
      }
    }, 40);
  }
  function confirm() {
    if (disabled || completed.current) return;
    Alert.alert(confirmationTitle, confirmationMessage, [
      { text: 'Keep protecting', style: 'cancel' },
      { text: confirmationAction, onPress: onComplete },
    ]);
  }
  return (
    <View style={styles.stack}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={title}
        accessibilityHint="Hold for two and a half seconds, or tap to confirm."
        accessibilityState={{ disabled: !!disabled }}
        disabled={disabled}
        onPressIn={screenReader ? undefined : begin}
        onPressOut={cancel}
        onTouchCancel={cancel}
        onPress={screenReader ? confirm : undefined}
        accessibilityActions={[{ name: 'activate', label: confirmationTitle }]}
        onAccessibilityAction={event => {
          if (event.nativeEvent.actionName === 'activate') confirm();
        }}
        style={[
          local.button,
          {
            backgroundColor: colors.surfaceElevated,
            borderColor: colors.border,
          },
        ]}
      >
        <View
          pointerEvents="none"
          style={[
            local.fill,
            {
              width: `${progress * 100}%`,
              backgroundColor: colors.warningSoft,
            },
          ]}
        />
        <Pause size={20} color={colors.text} />
        <Text style={[styles.body, { color: colors.text }]}>
          {progress > 0
            ? `Keep holding · ${Math.round(progress * 100)}%`
            : title}
        </Text>
      </Pressable>
      <Text style={[styles.small, local.caption]}>
        Hold for 2.5 seconds. Release early to cancel.
      </Text>
    </View>
  );
}
const local = StyleSheet.create({
  button: {
    minHeight: 56,
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 12,
  },
  fill: { position: 'absolute', left: 0, top: 0, bottom: 0 },
  caption: { textAlign: 'center' },
});
