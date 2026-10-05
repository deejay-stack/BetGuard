import React from 'react';
import { Alert, Linking, Text, View } from 'react-native';
import { Moon, Sun, Trash2, ExternalLink } from 'lucide-react-native';
import { BrandLogo } from '../components/BrandLogo';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Button, Card, Notice, Page } from '../components/ui';
import { useTheme } from '../state/ThemeContext';
export function SettingsScreen() {
  const { styles, mode, setMode, saving, error } = useTheme();
  const { clearHistory, busy, available } = useBetGuard();
  return (
    <Page
      title="Make it yours."
      subtitle="Understand what protection covers and how your data is used."
    >
      <Card>
        <Text accessibilityRole="header" style={styles.heading}>
          Appearance
        </Text>
        <Text accessibilityLiveRegion="polite" style={styles.body}>
          Current theme: {mode === 'dark' ? 'Dark' : 'Light'}
        </Text>
        <Button
          title={
            mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
          }
          icon={mode === 'dark' ? Sun : Moon}
          secondary
          disabled={saving}
          onPress={() => {
            void setMode(mode === 'dark' ? 'light' : 'dark');
          }}
        />
        <Text style={styles.small}>
          Starts with your device appearance. Your chosen theme is saved on this
          phone.
        </Text>
        {error && <Notice text={error} tone="error" />}
      </Card>
      <Card>
        <Badge text="DEVELOPMENT BUILD" />
        <Text style={styles.heading}>Protection coverage</Text>
        <Text style={styles.body}>
          Manual hostname rules apply to this phone’s new IPv4 UDP DNS requests
          through BetGuard. Other devices on the same Wi-Fi are not affected.
        </Text>
        <Text style={styles.body}>
          Encrypted DNS, DNS over TCP, direct IP connections, cached DNS
          answers, and existing connections are outside this filter’s coverage.
          It does not inspect encrypted page contents.
        </Text>
        <Text style={styles.body}>
          BetGuard does not restart protection automatically after a reboot or
          process termination. Reopen BetGuard and enable it again.
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
          questions. Check Link sends only the hostname to the classification
          service. Catalog and model results do not change your manual rules.
        </Text>
        <Text style={styles.body}>
          Optional online detection sends DNS hostnames to BetGuard while protection
          runs. Local rules take priority. High confidence detections are blocked;
          uncertain ML warnings remain allowed and appear in History. Detection
          errors return a resolution error. Choose manual rules only for offline use.
        </Text>
        <Button
          title="Clear local history"
          icon={Trash2}
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
          icon={ExternalLink}
          secondary
          onPress={() => {
            void Linking.openSettings().catch(() =>
              Alert.alert(
                'Settings unavailable',
                'Open Android Settings and select BetGuard.',
              ),
            );
          }}
        />
      </Card>
      <Card>
        <View style={styles.row}>
          <BrandLogo size={52} />
          <View style={styles.flex}>
            <Text accessibilityRole="header" style={styles.heading}>
              About BetGuard
            </Text>
            <Text style={styles.small}>0.1.0 · Development Build</Text>
          </View>
        </View>
        <Text style={styles.body}>
          More control over website access on this phone. Local manual rules and
          optional reviewed catalog and model checks. No account is required.
        </Text>
      </Card>
    </Page>
  );
}
