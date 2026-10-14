import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Button, Empty, Loading, Page } from '../components/ui';
import { ActivityRow, activityKind } from '../components/ActivityRow';
import { useTheme } from '../state/ThemeContext';
import { useRouterProtection } from '../state/RouterProtectionContext';

const filters = ['All', 'Blocked', 'Warnings', 'Allowed', 'Other'] as const;
export function HistoryScreen() {
  const { styles } = useTheme();
  const { snapshot, available } = useBetGuard();
  const router = useRouterProtection();
  const [filter, setFilter] = useState<(typeof filters)[number]>('All');
  const [source, setSource] = useState<
    'All protection' | 'Device' | 'Hotspot' | 'Router'
  >('All protection');
  const events =
    [...(snapshot?.history ?? []), ...(router?.snapshot?.history ?? [])]
      .sort((a, b) => b.createdAt - a.createdAt)
      .filter(
        item =>
          (filter === 'All' || activityKind(item.kind) === filter) &&
          (source === 'All protection' ||
            (item.kind.startsWith('router_')
              ? source === 'Router'
              : item.kind.startsWith('network_')
              ? source === 'Hotspot'
              : source === 'Device')),
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
      <View style={styles.wrap}>
        {(['All protection', 'Device', 'Hotspot', 'Router'] as const).map(
          option => (
            <Button
              key={option}
              title={option}
              secondary={source !== option}
              selected={source === option}
              onPress={() => setSource(option)}
            />
          ),
        )}
      </View>
      <Text style={styles.small}>
        Device and Router events record DNS outcomes. Hotspot events record
        proxy decisions and identify the client IP. Warning requests remain
        allowed. Allowed is not a safety label or proof that a page loaded.
      </Text>
      {!snapshot && available && <Loading />}
      {(snapshot || router?.snapshot) && !events.length && (
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
              <ActivityRow
                key={`${item.protection ?? 'device'}-${item.id}`}
                item={item}
              />
            ))}
          </View>
        ))}
      </View>
    </Page>
  );
}
