import React from 'react';
import { Text, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Card, Empty, Loading, Page } from '../components/ui';
import { useTheme } from '../state/ThemeContext';
const labels: Record<string, string> = {
  dns_blocked: 'BLOCKED BY RULE',
  dns_detection_blocked: 'BLOCKED BY DETECTION',
  dns_warning: 'DETECTION WARNING — ALLOWED',
  dns_forwarded: 'UPSTREAM DNS RESPONSE',
  dns_error: 'RESOLUTION ERROR',
  rule_saved: 'RULE SAVED',
  rule_changed: 'RULE UPDATED',
  rule_removed: 'OVERRIDE REMOVED',
  link_check: 'LINK CHECK',
  service: 'PROTECTION',
  network: 'NETWORK',
};
export function HistoryScreen() {
  const { styles } = useTheme();
  const { snapshot, available } = useBetGuard();
  return (
    <Page
      title="What happened."
      subtitle="The last 200 events, stored only on this phone."
    >
      <Text style={styles.body}>
        A saved rule is a setting change. “Blocked by rule” appears only after a
        blocking DNS response is written. An upstream response does not prove
        that a website loaded or is safe.
      </Text>
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
                item.kind === 'dns_blocked' || item.kind === 'dns_detection_blocked'
                  ? 'error'
                  : item.kind === 'dns_error' || item.kind === 'dns_warning'
                  ? 'warning'
                  : 'primary'
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
