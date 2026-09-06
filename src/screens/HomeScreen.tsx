import React from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import { Shield, ShieldOff, ArrowUpRight } from 'lucide-react-native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { stateLabels } from '../state/types';
import { Badge, Button, Card, Loading, Notice, Page } from '../components/ui';
import { colors, styles } from '../theme';
export function HomeScreen({ navigation }: BottomTabScreenProps<Tabs, 'Home'>) {
  const { snapshot, available, busy, error, start, stop } = useBetGuard();
  const enabled =
    snapshot?.state === 'active' || snapshot?.state === 'degraded';
  const uncertain = available && !snapshot && !!error;
  function enable() {
    Alert.alert(
      'Enable DNS filtering?',
      'BetGuard will request Android VPN permission. It filters this phone’s supported DNS requests using your rules. Allowed queries go to Cloudflare DNS (1.1.1.1). Encrypted DNS and existing connections may bypass these rules. Gambling classification is not connected yet.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Enable',
          onPress: () => {
            void start();
          },
        },
      ],
    );
  }
  const recentBlocked =
    snapshot?.history.filter(e => e.kind === 'dns_blocked').length ?? 0;
  return (
    <Page
      title="A little more control."
      subtitle="Manage the websites you want to access."
    >
      <View style={local.hero}>
        <View style={styles.spread}>
          <Text style={local.eyebrow}>ON THIS PHONE</Text>
          <Badge
            text={
              !snapshot
                ? 'STATUS UNKNOWN'
                : enabled
                ? 'DNS FILTER'
                : 'NOT FILTERING'
            }
            tone={snapshot?.state === 'active' ? 'green' : 'amber'}
          />
        </View>
        <View style={local.shield}>
          {enabled ? (
            <Shield size={44} color="#B6CAFF" strokeWidth={1.4} />
          ) : (
            <ShieldOff size={44} color="#B6CAFF" strokeWidth={1.4} />
          )}
        </View>
        <Text accessibilityLiveRegion="polite" style={local.heroTitle}>
          {snapshot
            ? stateLabels[snapshot.state]
            : uncertain
            ? 'Status unavailable'
            : available
            ? 'Reading protection status…'
            : 'Android build required'}
        </Text>
        <Text style={local.heroBody}>
          {snapshot?.detail ??
            'Protection status comes from the native service.'}
        </Text>
        <Button
          title={
            enabled || uncertain ? 'Turn off protection' : 'Enable protection'
          }
          onPress={
            enabled || uncertain
              ? () => {
                  void stop();
                }
              : enable
          }
          busy={busy || snapshot?.state === 'starting'}
          disabled={!available || (!snapshot && !uncertain)}
        />
      </View>
      {!snapshot && available && <Loading />}
      <View style={styles.row}>
        <View style={[styles.card, styles.flex]}>
          <Text style={local.metric}>{snapshot?.rules.length ?? '—'}</Text>
          <Text style={styles.small}>Saved site rules</Text>
        </View>
        <View style={[styles.card, styles.flex]}>
          <Text style={local.metric}>{snapshot ? recentBlocked : '—'}</Text>
          <Text style={styles.small}>Blocked DNS requests*</Text>
        </View>
      </View>
      <Text style={styles.small}>
        *Within the last 200 history entries. Requests are not unique websites
        or visits.
      </Text>
      <Card>
        <View style={styles.spread}>
          <Text style={styles.heading}>Choose your boundaries</Text>
          <ArrowUpRight size={22} color={colors.blue} />
        </View>
        <Text style={styles.body}>
          Add a block rule, allow a site again, or remove an override. You stay
          in control.
        </Text>
        <Button
          title="Manage site rules"
          secondary
          onPress={() => navigation.navigate('Sites')}
        />
      </Card>
      <Notice text="This first prototype tests manual blocking. Automatic gambling detection will follow after the model is trained and evaluated." />
    </Page>
  );
}
const local = StyleSheet.create({
  hero: {
    backgroundColor: colors.navy,
    borderRadius: 24,
    padding: 22,
    gap: 18,
  },
  eyebrow: {
    fontSize: 10,
    fontWeight: '700',
    color: '#B5C4DD',
    letterSpacing: 1.5,
  },
  shield: {
    width: 76,
    height: 76,
    borderRadius: 24,
    backgroundColor: '#253E68',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 6,
  },
  heroTitle: {
    fontSize: 25,
    lineHeight: 31,
    fontWeight: '700',
    letterSpacing: -0.6,
    color: colors.white,
  },
  heroBody: { fontSize: 13, lineHeight: 21, color: '#C1CFE3' },
  metric: { fontSize: 28, fontWeight: '700', color: colors.ink },
});
