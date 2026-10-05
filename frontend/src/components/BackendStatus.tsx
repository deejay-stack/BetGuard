import React, { useEffect, useRef, useState } from 'react';
import { Text } from 'react-native';
import { checkReadiness } from '../api/health';
import { useTheme } from '../state/ThemeContext';
import { Button, Card } from './ui';

export function BackendStatus() {
  const { styles } = useTheme();
  const [status, setStatus] = useState<
    'Not checked' | 'Checking' | 'Connected' | 'Unavailable'
  >('Not checked');
  const pending = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      pending.current?.abort();
      pending.current = null;
    },
    [],
  );
  async function check() {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setStatus('Checking');
    try {
      await checkReadiness(controller.signal);
      if (!controller.signal.aborted) setStatus('Connected');
    } catch {
      if (!controller.signal.aborted) setStatus('Unavailable');
    } finally {
      if (pending.current === controller) pending.current = null;
    }
  }
  return (
    <Card>
      <Text style={styles.small} accessibilityLiveRegion="polite">
        Backend: {status}
      </Text>
      <Button
        title="Check backend connection"
        secondary
        busy={status === 'Checking'}
        onPress={() => {
          void check();
        }}
      />
      <Text style={styles.small}>
        Development check only. Local protection works independently.
      </Text>
    </Card>
  );
}
