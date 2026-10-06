import React, { useState } from 'react';
import { Alert, Linking, Text, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { Trash2, ExternalLink } from 'lucide-react-native';
import { BrandLogo } from '../components/BrandLogo';
import { useBetGuard } from '../state/BetGuardContext';
import { Button, Card, Notice, Page } from '../components/ui';
import { useTheme, type ThemePreference } from '../state/ThemeContext';
import { API_BASE_URL } from '../api/config';
import { HowItWorks } from '../components/HowItWorks';
import appVersion from '../../app.version.json';
import { BottomSheet } from '../components/BottomSheet';
import { Badge } from '../components/ui';

export function SettingsScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Settings'>;
}) {
  const { styles, mode, preference, setMode, saving, error } = useTheme();
  const { snapshot, clearHistory, busy, available } = useBetGuard();
  const [advanced, setAdvanced] = useState(false);
  return (
    <Page title="Settings" subtitle="Protection, appearance, and your privacy.">
      <HowItWorks />
      <View style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>
          Protection
        </Text>
        <Text style={styles.body}>
          {snapshot?.state === 'active'
            ? `Running: ${
                snapshot.detectionEnabled
                  ? 'Smart protection'
                  : 'On-device rules'
              }.`
            : snapshot?.state === 'degraded'
            ? 'Protection needs attention. Open Home to see the problem.'
            : 'Protection is not confirmed on. Choose a mode and enable it on Home.'}
        </Text>
        <Text style={styles.small}>
          On-device rules need no BetGuard server. Smart protection needs a
          reachable online service. Browsing still needs internet in both modes.
        </Text>
        <Button
          title="DNS protection details"
          secondary
          onPress={() => setAdvanced(true)}
        />
        <Button
          title="Manage protection"
          secondary
          onPress={() => navigation?.navigate('Home')}
          disabled={!navigation}
        />
        {!API_BASE_URL && (
          <Notice text="This APK is ready for on-device rules. Smart protection needs a BetGuard service to be set up." />
        )}
      </View>
      <BottomSheet
        visible={advanced}
        title="DNS protection details"
        onClose={() => setAdvanced(false)}
      >
        <Badge
          text={
            snapshot?.state === 'active'
              ? 'ACTIVE'
              : snapshot?.state === 'degraded'
              ? 'ATTENTION REQUIRED'
              : 'NOT CONFIRMED ACTIVE'
          }
          tone={snapshot?.state === 'active' ? 'success' : 'warning'}
        />
        <Text style={styles.body}>
          The DNS filter helps block restricted hostnames before supported
          connections begin. Your saved rules take priority. Smart mode adds
          online detection.
        </Text>
        <Text style={styles.small}>
          Resolver: Cloudflare (1.1.1.1). Only new IPv4 UDP DNS requests through
          the virtual resolver are covered. Private/encrypted DNS, other
          resolvers, cached addresses, direct IP access and existing connections
          may bypass filtering.
        </Text>
        <Button
          title="Close DNS protection details"
          secondary
          onPress={() => setAdvanced(false)}
        />
      </BottomSheet>
      <View style={styles.divider} />
      <View style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>
          Website rules
        </Text>
        <Text style={styles.body}>
          {snapshot?.rules.length ?? 0} choices saved on this phone. Your
          matching rules take priority over automatic detection.
        </Text>
        <Button
          title="Manage website rules"
          secondary
          onPress={() => navigation?.navigate('Sites')}
          disabled={!navigation}
        />
      </View>
      <Card>
        <Text accessibilityRole="header" style={styles.heading}>
          Appearance
        </Text>
        <View style={styles.row}>
          {(['system', 'light', 'dark'] as ThemePreference[]).map(option => (
            <View key={option} style={styles.flex}>
              <Button
                title={option.charAt(0).toUpperCase() + option.slice(1)}
                accessibilityLabel={`Use ${option} appearance`}
                secondary={preference !== option}
                selected={preference === option}
                disabled={saving}
                onPress={() => {
                  void setMode(option);
                }}
              />
            </View>
          ))}
        </View>
        <Text accessibilityLiveRegion="polite" style={styles.small}>
          Current theme: {mode === 'dark' ? 'Dark' : 'Light'}
          {preference === 'system' ? ' (follows your device)' : ''}. Saved on
          this phone.
        </Text>
        {error && <Notice text={error} tone="error" />}
      </Card>
      <View style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>
          Notifications
        </Text>
        <Text style={styles.body}>
          Android VPN permission enables filtering. Notifications provide the
          ongoing status and a Stop action.
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
      </View>
      <View style={styles.divider} />
      <View style={styles.stack}>
        <Text accessibilityRole="header" style={styles.heading}>
          Privacy
        </Text>
        <Text style={styles.body}>
          Rules and the latest 200 activity entries stay on this phone. Clearing
          history keeps your rules. No account is required.
        </Text>
        <Text style={styles.small}>
          Check Link and optional online detection send only hostnames to
          BetGuard. Allowed DNS questions go to Cloudflare (1.1.1.1) using
          ordinary DNS, which your network and resolver can observe. Online
          detection errors return a DNS error; manual rules work offline.
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
      </View>
      <View style={styles.divider} />
      <View style={styles.row}>
        <BrandLogo size={40} />
        <View style={styles.flex}>
          <Text accessibilityRole="header" style={styles.heading}>
            About BetGuard
          </Text>
          <Text style={styles.small}>
            {appVersion.versionName} · Build {appVersion.versionCode} ·{' '}
            {__DEV__ ? 'USB development' : 'Saved APK'}
          </Text>
          <Text style={styles.small}>
            Your rules on the phone. Optional smart checks on the server.
          </Text>
        </View>
      </View>
    </Page>
  );
}
