import React, { useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import type { LinkResult } from '../state/types';
import { Badge, Button, Card, Notice, Page } from '../components/ui';
import { colors, styles } from '../theme';
export function CheckScreen() {
  const [input, setInput] = useState('');
  const [result, setResult] = useState<LinkResult | null>(null);
  const { check, save, available, busy } = useBetGuard();
  async function inspect() {
    const next = await check(input);
    setResult(next ?? null);
  }
  async function change(action: 'block' | 'allow') {
    if (!result) {
      return;
    }
    const domain = await save(result.domain, action, false);
    if (domain) {
      const next = await check(domain);
      setResult(next ?? null);
    }
  }
  return (
    <Page
      title="Check a link."
      subtitle="See the hostname and its current access rule."
    >
      <Card>
        <Text style={styles.heading}>Website link</Text>
        <TextInput
          accessibilityLabel="Link to check"
          style={styles.input}
          value={input}
          onChangeText={v => {
            setInput(v);
            setResult(null);
          }}
          placeholder="https://example.com"
          placeholderTextColor={colors.muted}
          keyboardType="url"
          autoCapitalize="none"
          autoCorrect={false}
          maxLength={2048}
        />
        <Button
          title="Check link"
          busy={busy}
          disabled={!available || !input.trim()}
          onPress={() => {
            void inspect();
          }}
        />
        <Text style={styles.small}>
          Only the hostname is retained. Page paths, passwords, and query tokens
          are not stored.
        </Text>
      </Card>
      <Notice text="Gambling classification is not connected yet. Checking a link currently validates its hostname and shows your manual rule." />
      {result && (
        <Card>
          <Badge text="CLASSIFICATION UNKNOWN" tone="amber" />
          <Text selectable style={styles.heading}>
            {result.domain}
          </Text>
          <Text style={styles.body}>
            {result.matchedDomain
              ? `Matching rule: ${result.action} (${result.matchedDomain}).`
              : 'No matching manual rule. Access is allowed by default.'}
          </Text>
          <Text style={styles.small}>
            Checked {new Date(result.checkedAt).toLocaleString()}. This result
            does not establish that a website is safe.
          </Text>
          <View style={styles.row}>
            <View style={styles.flex}>
              <Button
                title="Block site"
                disabled={busy}
                onPress={() => {
                  void change('block');
                }}
              />
            </View>
            <View style={styles.flex}>
              <Button
                title="Allow site"
                secondary
                disabled={busy}
                onPress={() => {
                  void change('allow');
                }}
              />
            </View>
          </View>
        </Card>
      )}
    </Page>
  );
}
