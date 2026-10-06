import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { HistoryItem } from '../state/types';
import { useTheme } from '../state/ThemeContext';
import { Badge } from './ui';
import {
  Ban,
  CheckCircle2,
  TriangleAlert,
  Activity,
} from 'lucide-react-native';

export function activityKind(
  kind: string,
): 'Blocked' | 'Warnings' | 'Allowed' | 'Other' {
  return ['dns_blocked', 'dns_detection_blocked'].includes(kind)
    ? 'Blocked'
    : kind === 'dns_warning'
    ? 'Warnings'
    : kind === 'dns_forwarded'
    ? 'Allowed'
    : 'Other';
}
export function relativeTime(time: number): string {
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  return minutes < 1
    ? 'Just now'
    : minutes < 60
    ? `${minutes} min ago`
    : minutes < 1440
    ? `${Math.floor(minutes / 60)} hr ago`
    : new Date(time).toLocaleDateString();
}
export function ActivityRow({ item }: { item: HistoryItem }) {
  const { colors, styles } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const category = activityKind(item.kind);
  const Icon =
    category === 'Blocked'
      ? Ban
      : category === 'Warnings' || item.kind === 'dns_error'
      ? TriangleAlert
      : category === 'Allowed'
      ? CheckCircle2
      : Activity;
  const color =
    category === 'Blocked'
      ? colors.blocked
      : category === 'Warnings' || item.kind === 'dns_error'
      ? colors.review
      : category === 'Allowed'
      ? colors.allowed
      : colors.primary;
  const label =
    category === 'Warnings'
      ? 'WARNING · ALLOWED'
      : category !== 'Other'
      ? category.toUpperCase()
      : item.kind === 'dns_error'
      ? 'RESOLUTION ERROR'
      : item.kind.startsWith('rule_')
      ? 'RULE CHANGE'
      : item.kind === 'link_check'
      ? 'LINK CHECK'
      : 'PROTECTION';
  const reason =
    item.kind === 'dns_detection_blocked'
      ? item.detail.includes('verified_gambling')
        ? 'Known gambling domain'
        : 'High risk detection'
      : item.kind === 'dns_blocked'
      ? 'Your block rule'
      : category === 'Warnings'
      ? 'Review suggested; access stays allowed'
      : category === 'Allowed'
      ? 'DNS response returned'
      : item.kind === 'dns_error'
      ? 'Request could not be resolved'
      : item.kind.startsWith('rule_')
      ? 'Saved rules updated on this phone'
      : 'Local protection event';
  return (
    <View style={[local.row, { borderBottomColor: colors.border }]}>
      <View style={styles.spread}>
        <Icon size={20} color={color} accessible={false} />
        <Text selectable style={[styles.heading, styles.flex]}>
          {item.domain || 'DNS protection'}
        </Text>
        <Text style={styles.small}>{relativeTime(item.createdAt)}</Text>
      </View>
      <View style={styles.wrap}>
        <Badge
          text={label}
          tone={
            category === 'Blocked'
              ? 'error'
              : category === 'Warnings' || item.kind === 'dns_error'
              ? 'warning'
              : category === 'Allowed'
              ? 'success'
              : 'primary'
          }
        />
        <Text style={styles.small}>{reason}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${expanded ? 'Hide' : 'Show'} details for event ${
          item.id
        }`}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded(!expanded)}
        style={local.details}
      >
        <Text style={[styles.small, { color: colors.primary }]}>
          {expanded ? 'Hide details' : 'Details'}
        </Text>
      </Pressable>
      {expanded && (
        <Text selectable style={styles.small}>
          {item.detail}
          {'\n'}
          {new Date(item.createdAt).toLocaleString()}
        </Text>
      )}
    </View>
  );
}
const local = StyleSheet.create({
  row: { paddingVertical: 14, borderBottomWidth: 1, gap: 8 },
  details: { minHeight: 44, justifyContent: 'center' },
});
