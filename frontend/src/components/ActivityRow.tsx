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
  return ['dns_blocked', 'dns_detection_blocked', 'network_blocked'].includes(
    kind,
  )
    ? 'Blocked'
    : ['dns_warning', 'network_warning'].includes(kind)
    ? 'Warnings'
    : ['dns_forwarded', 'network_allowed'].includes(kind)
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
  const network = item.kind.startsWith('network_');
  const Icon =
    category === 'Blocked'
      ? Ban
      : category === 'Warnings' ||
        ['dns_error', 'network_error'].includes(item.kind)
      ? TriangleAlert
      : category === 'Allowed'
      ? CheckCircle2
      : Activity;
  const color =
    category === 'Blocked'
      ? colors.blocked
      : category === 'Warnings' ||
        ['dns_error', 'network_error'].includes(item.kind)
      ? colors.review
      : category === 'Allowed'
      ? colors.allowed
      : colors.primary;
  const label =
    category === 'Warnings'
      ? 'WARNING · ALLOWED'
      : category !== 'Other'
      ? category.toUpperCase()
      : ['dns_error', 'network_error'].includes(item.kind)
      ? network
        ? 'PROXY ERROR'
        : 'RESOLUTION ERROR'
      : item.kind.startsWith('rule_')
      ? 'RULE CHANGE'
      : item.kind === 'link_check'
      ? 'LINK CHECK'
      : 'PROTECTION';
  const reason =
    item.kind === 'network_blocked'
      ? item.decisionSource === 'user_blocklist'
        ? 'Your block rule'
        : item.decisionSource === 'verified_gambling_blocklist'
        ? 'Known gambling domain'
        : 'High risk detection'
      : item.kind === 'dns_detection_blocked'
      ? item.detail.includes('verified_gambling')
        ? 'Known gambling domain'
        : 'High risk detection'
      : item.kind === 'dns_blocked'
      ? 'Your block rule'
      : category === 'Warnings'
      ? 'Review suggested; access stays allowed'
      : category === 'Allowed'
      ? network
        ? 'Proxy connection permitted'
        : 'DNS response returned'
      : ['dns_error', 'network_error'].includes(item.kind)
      ? 'Request could not be resolved'
      : item.kind.startsWith('rule_')
      ? 'Saved rules updated on this phone'
      : 'Local protection event';
  return (
    <View style={[local.row, { borderBottomColor: colors.border }]}>
      <View style={styles.spread}>
        <Icon size={20} color={color} accessible={false} />
        <Text selectable style={[styles.heading, styles.flex]}>
          {item.domain || (network ? 'Network Protection' : 'DNS protection')}
        </Text>
        <Text style={styles.small}>{relativeTime(item.createdAt)}</Text>
      </View>
      <View style={styles.wrap}>
        <Badge
          text={label}
          tone={
            category === 'Blocked'
              ? 'error'
              : category === 'Warnings' ||
                ['dns_error', 'network_error'].includes(item.kind)
              ? 'warning'
              : category === 'Allowed'
              ? 'success'
              : 'primary'
          }
        />
        <Text style={styles.small}>{reason}</Text>
        <Badge text={network ? 'NETWORK' : 'DEVICE'} />
      </View>
      {network && (
        <Text selectable style={styles.small}>
          Client: {item.clientIp ?? 'Unavailable'} · Source:{' '}
          {item.decisionSource ?? 'Unavailable'}
        </Text>
      )}
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
