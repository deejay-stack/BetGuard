import React from 'react';
import { Text, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Card, Empty, Loading, Page } from '../components/ui';
import { styles } from '../theme';
const labels: Record<string, string> = {
  dns_blocked: 'DNS BLOCKED',
  dns_forwarded: 'DNS RESPONSE',
  dns_error: 'DNS ERROR',
  rule_saved: 'RULE SAVED',
  rule_removed: 'OVERRIDE REMOVED',
  link_check: 'LINK CHECK',
  service: 'PROTECTION',
  network: 'NETWORK',
};
export function HistoryScreen() {
  const { snapshot, available } = useBetGuard();
  return (
    <Page
      title="What happened."
      subtitle="The last 200 events, stored only on this phone."
    >
      {!snapshot && available && <Loading />}
      {snapshot?.history.length === 0 && (
        <Card>
          <Empty
            title="A fresh start"
            body="Saved rules, link checks, and DNS request outcomes will appear here as they happen."
          />
        </Card>
      )}
      {snapshot?.history.map(item => (
        <Card key={item.id}>
          <View style={styles.spread}>
            <Badge
              text={labels[item.kind] ?? item.kind}
              tone={
                item.kind === 'dns_blocked'
                  ? 'red'
                  : item.kind === 'dns_error'
                  ? 'amber'
                  : 'blue'
              }
            />
            <Text style={styles.small}>
              {new Date(item.createdAt).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
          </View>
          {!!item.domain && (
            <Text selectable style={styles.heading}>
              {item.domain}
            </Text>
          )}
          <Text style={styles.body}>{item.detail}</Text>
          <Text style={styles.small}>
            {new Date(item.createdAt).toLocaleDateString()}
          </Text>
        </Card>
      ))}
    </Page>
  );
}
