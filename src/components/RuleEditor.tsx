import React, { useState } from 'react';
import { Switch, Text, TextInput, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { colors, styles } from '../theme';
import { Badge, Button, Card } from './ui';
export function RuleEditor() {
  const [input, setInput] = useState('');
  const [subdomains, setSubdomains] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const { save, busy, available } = useBetGuard();
  async function submit(action: 'block' | 'allow') {
    const host = await save(input, action, subdomains);
    if (host) {
      setSaved(`${host}: ${action} rule saved`);
      setInput('');
    }
  }
  return (
    <Card>
      <Text style={styles.heading}>Add a site rule</Text>
      <Text style={styles.body}>
        Paste a link or enter a hostname. Rules apply to the hostname, including
        all its pages.
      </Text>
      <TextInput
        accessibilityLabel="Website link or hostname"
        placeholder="example.com"
        placeholderTextColor={colors.muted}
        value={input}
        onChangeText={v => {
          setInput(v);
          setSaved(null);
        }}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        maxLength={2048}
        style={styles.input}
      />
      <View style={styles.spread}>
        <View style={styles.flex}>
          <Text style={styles.body}>Include subdomains</Text>
          <Text style={styles.small}>Also match www and other subdomains.</Text>
        </View>
        <Switch
          accessibilityLabel="Include subdomains"
          value={subdomains}
          onValueChange={setSubdomains}
          trackColor={{ true: colors.blue, false: colors.border }}
        />
      </View>
      <View style={styles.row}>
        <View style={styles.flex}>
          <Button
            title="Block site"
            onPress={() => {
              void submit('block');
            }}
            disabled={!input.trim() || !available || busy}
          />
        </View>
        <View style={styles.flex}>
          <Button
            title="Allow site"
            secondary
            onPress={() => {
              void submit('allow');
            }}
            disabled={!input.trim() || !available || busy}
          />
        </View>
      </View>
      {saved && <Badge text={saved} tone="green" />}
      <Text style={styles.small}>
        Saved rules are checked on new covered DNS requests. Existing
        connections and cached pages can remain accessible.
      </Text>
    </Card>
  );
}
