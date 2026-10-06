import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Button, Empty, Loading, Page } from '../components/ui';
import { ActivityRow, activityKind } from '../components/ActivityRow';
import { useTheme } from '../state/ThemeContext';

const filters = ['All', 'Blocked', 'Warnings', 'Allowed', 'Other'] as const;
export function HistoryScreen() {
  const { styles } = useTheme();
  const { snapshot, available } = useBetGuard();
  const [filter, setFilter] = useState<(typeof filters)[number]>('All');
  const events =
    snapshot?.history.filter(
      item => filter === 'All' || activityKind(item.kind) === filter,
    ) ?? [];
  const groups = events.reduce<Record<string, typeof events>>((all, item) => {
    const date = new Date(item.createdAt);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    const label =
      date.toDateString() === today.toDateString()
        ? 'Today'
        : date.toDateString() === yesterday.toDateString()
        ? 'Yesterday'
        : date.toLocaleDateString();
    (all[label] ??= []).push(item);
    return all;
  }, {});
  return (
    <Page title="Activity" subtitle="See what protection actually handled.">
      <View style={styles.wrap}>
        {filters.map(option => (
          <Button
            key={option}
            title={option}
            secondary={filter !== option}
            selected={filter === option}
            onPress={() => setFilter(option)}
          />
        ))}
      </View>
      <Text style={styles.small}>
        Blocked records a DNS response from the filter. Warning requests remain
        allowed. Allowed is a DNS outcome, not a safety label or proof that a
        page loaded.
      </Text>
      {!snapshot && available && <Loading />}
      {snapshot && !events.length && (
        <Empty
          title={
            filter === 'All'
              ? 'A fresh start'
              : `No ${filter.toLowerCase()} events`
          }
          body="Saved rules, link checks, and DNS request outcomes will appear here as they happen."
        />
      )}
      <View>
        {Object.entries(groups).map(([label, items]) => (
          <View key={label} style={styles.stack}>
            <Text accessibilityRole="header" style={styles.eyebrow}>
              {label.toUpperCase()}
            </Text>
            {items.map(item => (
              <ActivityRow key={item.id} item={item} />
            ))}
          </View>
        ))}
      </View>
    </Page>
  );
}
