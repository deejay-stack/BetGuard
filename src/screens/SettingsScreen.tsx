import React from 'react';
import { Alert, Linking, Text } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Button, Card, Page } from '../components/ui';
import { styles } from '../theme';
export function SettingsScreen() {
  const { clearHistory, busy, available } = useBetGuard();
  return (
    <Page
      title="Make it yours."
      subtitle="Understand what protection covers and how your data is used."
    >
      <Card>
        <Badge text="FIRST ANDROID PROTOTYPE" />
        <Text style={styles.heading}>Protection coverage</Text>
        <Text style={styles.body}>
          Manual hostname rules apply to this phone’s new IPv4 UDP DNS requests
          through BetGuard. Other devices on the same Wi-Fi are not affected.
        </Text>
        <Text style={styles.body}>
          Encrypted DNS, DNS over TCP, direct IP connections, cached DNS
          answers, and existing connections are outside this prototype’s
          coverage. It does not inspect encrypted page contents.
        </Text>
        <Text style={styles.body}>
          This prototype does not restart protection automatically after a
          reboot or process termination. Reopen BetGuard and enable it again.
        </Text>
      </Card>
      <Card>
        <Text style={styles.heading}>Your data</Text>
        <Text style={styles.body}>
          Rules and the latest 200 history entries stay on this phone. No
          account is required. Clearing history keeps your site rules.
        </Text>
        <Text style={styles.body}>
          Unblocked DNS questions are sent to Cloudflare’s resolver at 1.1.1.1
          using ordinary DNS. Your network and resolver can observe those
          questions. Gambling classification is not connected.
        </Text>
        <Button
          title="Clear local history"
          secondary
          disabled={!available || busy}
          onPress={() =>
            Alert.alert(
              'Clear history?',
              'This deletes the local event history. Your site rules will stay saved. New requests can create new events while protection is running.',
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Clear history',
                  style: 'destructive',
                  onPress: () => {
                    void clearHistory();
                  },
                },
              ],
            )
          }
        />
      </Card>
      <Card>
        <Text style={styles.heading}>Android permissions</Text>
        <Text style={styles.body}>
          VPN permission enables the filter. Notification permission makes its
          ongoing status and Stop action visible in the notification tray.
        </Text>
        <Button
          title="Open app settings"
          secondary
          onPress={() => {
            void Linking.openSettings();
          }}
        />
      </Card>
      <Text style={styles.small}>BetGuard · 0.1.0 · Feasibility build</Text>
    </Page>
  );
}
