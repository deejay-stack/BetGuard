import { Ban, Check, Trash2, Plus, Search } from 'lucide-react-native';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, Text, TextInput, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Button, Card, Empty, Loading, Page } from '../components/ui';
import { BottomSheet } from '../components/BottomSheet';
import { RuleEditor } from '../components/RuleEditor';
import { useTheme } from '../state/ThemeContext';
export function SitesScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Sites'>;
}) {
  const { colors, styles, mode } = useTheme();
  const { snapshot, busy, available, save, remove } = useBetGuard();
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const [filter, setFilter] = useState<'All' | 'Blocked' | 'Allowed'>('All');
  const [expanded, setExpanded] = useState<string | null>(null);
  useEffect(
    () => navigation?.addListener('blur', () => setAdding(false)),
    [navigation],
  );
  const rules =
    snapshot?.rules.filter(
      rule =>
        rule.domain.toLowerCase().includes(query.trim().toLowerCase()) &&
        (filter === 'All' ||
          rule.action === (filter === 'Blocked' ? 'block' : 'allow')),
    ) ?? [];
  return (
    <Page title="Protection" subtitle="Your website choices always come first.">
      <View style={styles.spread}>
        <View style={styles.flex}>
          <Text style={styles.heading}>Website rules</Text>
          <Text style={styles.small}>
            {snapshot?.rules.length ?? 0} saved on this phone
          </Text>
        </View>
        <Button
          title="Add website"
          icon={Plus}
          disabled={!available || busy}
          onPress={() => setAdding(true)}
        />
      </View>
      <View style={styles.row}>
        <Search size={20} color={colors.textMuted} />
        <TextInput
          style={[
            styles.input,
            styles.flex,
            focused && { borderColor: colors.primary },
          ]}
          accessibilityLabel="Search website rules"
          placeholder="Search websites…"
          placeholderTextColor={colors.textMuted}
          value={query}
          onChangeText={setQuery}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          keyboardAppearance={mode}
          selectionColor={colors.primary}
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>
      <View style={styles.wrap}>
        {(['All', 'Blocked', 'Allowed'] as const).map(option => (
          <Button
            key={option}
            title={option}
            selected={filter === option}
            secondary={filter !== option}
            onPress={() => setFilter(option)}
          />
        ))}
      </View>
      <Text style={styles.small}>
        Save a rule, then enable protection on Home. Exact rules match one
        hostname; Include subdomains covers www and other subdomains.
      </Text>
      {!snapshot && available && <Loading />}
      {snapshot && !rules.length && (
        <Card>
          <Empty
            title={
              snapshot.rules.length === 0
                ? 'No websites added yet'
                : 'No matching websites'
            }
            body={
              snapshot.rules.length === 0
                ? 'Add a website to Block or Allow. Your saved choices take priority over automated detection.'
                : 'Try another search or choose a different filter.'
            }
          />
          {snapshot.rules.length === 0 && (
            <Button
              title="Add your first website"
              icon={Plus}
              disabled={!available || busy}
              onPress={() => setAdding(true)}
            />
          )}
        </Card>
      )}
      {rules.map(rule => (
        <View key={rule.domain} style={styles.ruleRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Manage rule for ${rule.domain}`}
            accessibilityState={{ expanded: expanded === rule.domain }}
            onPress={() =>
              setExpanded(expanded === rule.domain ? null : rule.domain)
            }
            style={[styles.spread, styles.ruleSummary]}
          >
            {rule.action === 'block' ? (
              <Ban size={22} color={colors.blocked} />
            ) : (
              <Check size={22} color={colors.allowed} />
            )}
            <View style={styles.flex}>
              <Text style={styles.heading}>{rule.domain}</Text>
              <Text style={styles.small}>
                {rule.includeSubdomains
                  ? 'Hostname + subdomains'
                  : 'Exact hostname'}
              </Text>
            </View>
            <Badge
              text={rule.action === 'block' ? 'BLOCKED' : 'ALLOWED'}
              tone={rule.action === 'block' ? 'error' : 'success'}
            />
          </Pressable>
          {expanded === rule.domain && (
            <View style={styles.wrap}>
              <Button
                title={
                  rule.includeSubdomains
                    ? 'Use exact hostname'
                    : 'Include subdomains'
                }
                secondary
                disabled={busy}
                onPress={() => {
                  void save(rule.domain, rule.action, !rule.includeSubdomains);
                }}
              />
              <Button
                title={rule.action === 'block' ? 'Allow site' : 'Block site'}
                icon={rule.action === 'block' ? Check : Ban}
                secondary
                disabled={busy}
                onPress={() => {
                  void save(
                    rule.domain,
                    rule.action === 'block' ? 'allow' : 'block',
                    rule.includeSubdomains,
                  );
                }}
              />
              <Button
                title="Remove rule"
                icon={Trash2}
                accessibilityLabel={`Remove rule for ${rule.domain}`}
                secondary
                disabled={busy}
                onPress={() =>
                  Alert.alert(
                    'Remove this override?',
                    'Another matching rule may still apply. Otherwise, Smart protection uses detection; On-device mode allows unmatched hostnames.',
                    [
                      { text: 'Cancel', style: 'cancel' },
                      {
                        text: 'Remove override',
                        style: 'destructive',
                        onPress: () => {
                          void remove(rule.domain);
                        },
                      },
                    ],
                  )
                }
              />
            </View>
          )}
        </View>
      ))}
      <Button
        title="Check a link"
        icon={Search}
        secondary
        disabled={!navigation}
        onPress={() => navigation?.navigate('Check')}
      />
      <BottomSheet
        visible={adding}
        title="Add website"
        onClose={() => setAdding(false)}
      >
        <RuleEditor onSaved={() => setAdding(false)} />
      </BottomSheet>
    </Page>
  );
}
