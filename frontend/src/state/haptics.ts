import { Platform, Vibration } from 'react-native';
// Only meaningful outcomes vibrate; ordinary navigation stays quiet.
export function haptic(kind: 'success' | 'blocked' | 'error') {
  if (Platform.OS !== 'android') return;
  try {
    Vibration.vibrate(
      kind === 'success'
        ? 20
        : kind === 'blocked'
        ? [0, 25, 70, 25]
        : [0, 35, 60, 35],
    );
  } catch {
    /* Feedback must never prevent a protection or rule action. */
  }
}
