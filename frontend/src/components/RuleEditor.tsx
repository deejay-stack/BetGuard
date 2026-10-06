import { Ban, Check } from 'lucide-react-native';
import React, { useState } from 'react';
import { Switch, Text, TextInput, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { useTheme } from '../state/ThemeContext';
import { Button } from './ui';
export function RuleEditor({ onSaved }: { onSaved?: () => void }) {
  const { colors, styles, mode } = useTheme();
  const [input, setInput] = useState('');
  const [subdomains, setSubdomains] = useState(false);
  const [focused, setFocused] = useState(false);
  const { save, busy, available } = useBetGuard();
  async function submit(action: 'block' | 'allow') {
    const host = await save(input, action, subdomains);
    if (host) {
      setInput('');
      onSaved?.();
    }
  }
  return (
    <View style={styles.stack}>
      <Text style={styles.heading}>Add a site rule</Text>
      <Text style={styles.body}>
        Paste a link or enter a hostname. Rules apply to the hostname, including
        all its pages.
      </Text>
      <TextInput
        accessibilityLabel="Website link or hostname"
        placeholder="example.com"
        placeholderTextColor={colors.textMuted}
        value={input}
        onChangeText={v => {
          setInput(v);
        }}
        keyboardAppearance={mode}
        selectionColor={colors.primary}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        maxLength={2048}
        editable={!busy}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        style={[styles.input, focused && { borderColor: colors.primary }]}
      />
      <View style={styles.spread}>
        <View style={styles.flex}>
          <Text style={styles.body}>Include subdomains</Text>
          <Text style={styles.small}>Also match www and other subdomains.</Text>
        </View>
        <Switch
          accessibilityLabel="Include subdomains"
          value={subdomains}
          disabled={busy}
          onValueChange={setSubdomains}
          trackColor={{ true: colors.primary, false: colors.border }}
        />
      </View>
      <View style={styles.row}>
        <View style={styles.flex}>
          <Button
            title="Block site"
            icon={Ban}
            onPress={() => {
              void submit('block');
            }}
            disabled={!input.trim() || !available || busy}
          />
        </View>
        <View style={styles.flex}>
          <Button
            title="Allow site"
            icon={Check}
            secondary
            onPress={() => {
              void submit('allow');
            }}
            disabled={!input.trim() || !available || busy}
          />
        </View>
      </View>
      <Text style={styles.small}>
        Saved rules are checked on new covered DNS requests. Existing
        connections and cached pages can remain accessible.
      </Text>
    </View>
  );
}
