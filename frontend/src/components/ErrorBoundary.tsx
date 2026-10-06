import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { lightColors } from '../theme';
import { logFailure } from '../state/nativeContract';

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    logFailure('render', error);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <View style={local.page}>
        <Text style={local.title}>Let’s try that again</Text>
        <Text style={local.body}>
          BetGuard couldn’t display this screen. Your saved rules are still on
          this phone. Reopen the app to confirm protection status.
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Try again"
          style={local.button}
          onPress={() => this.setState({ failed: false })}
        >
          <Text style={local.buttonText}>Try again</Text>
        </Pressable>
      </View>
    );
  }
}
const local = StyleSheet.create({
  page: {
    flex: 1,
    justifyContent: 'center',
    gap: 20,
    padding: 28,
    backgroundColor: lightColors.background,
  },
  title: { fontSize: 24, fontWeight: '700', color: lightColors.text },
  body: { fontSize: 15, lineHeight: 24, color: lightColors.textMuted },
  button: {
    minHeight: 52,
    justifyContent: 'center',
    alignItems: 'center',
    borderRadius: 16,
    backgroundColor: lightColors.primary,
  },
  buttonText: { color: lightColors.onPrimary, fontWeight: '700' },
});
