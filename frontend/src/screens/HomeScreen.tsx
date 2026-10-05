import React from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import {
  ShieldCheck,
  ShieldOff,
  ShieldAlert,
  CircleHelp,
  Clock3,
  ArrowUpRight,
} from 'lucide-react-native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { stateLabels } from '../state/types';
import { Badge, Button, Card, Loading, Notice, Page } from '../components/ui';
import type { ThemeColors } from '../theme';
import { useTheme } from '../state/ThemeContext';
export function HomeScreen({ navigation }: BottomTabScreenProps<Tabs, 'Home'>) {
  const { colors, styles } = useTheme();
  const local = makeLocal(colors);
  const { snapshot, available, busy, error, start, stop } = useBetGuard();
  const enabled =
    snapshot?.state === 'active' || snapshot?.state === 'degraded';
  const StatusIcon = !snapshot
    ? CircleHelp
    : snapshot.state === 'active'
    ? ShieldCheck
    : snapshot.state === 'starting' || snapshot.state === 'stopping'
    ? Clock3
    : snapshot.state === 'off'
    ? ShieldOff
    : ShieldAlert;
  const uncertain = available && !snapshot && !!error;
  function enable() {
    Alert.alert(
      'Enable DNS filtering?',
      'BetGuard will request Android VPN permission. Manual rules work offline. Online detection sends hostnames to BetGuard for blocklist/ML decisions; warnings remain allowed. If detection is unavailable, unmatched requests return a resolution error. Allowed queries go to Cloudflare DNS (1.1.1.1). Encrypted DNS and existing connections may bypass filtering.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Manual rules only',
          onPress: () => {
            void start();
          },
        },
        {
          text: 'Enable online detection',
          onPress: () => {
            void start(true);
          },
        },
      ],
    );
  }
  const recentBlocked =
    snapshot?.history.filter(e => e.kind === 'dns_blocked' || e.kind === 'dns_detection_blocked').length ?? 0;
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
                : snapshot.state === 'active'
                ? 'DNS FILTER RUNNING'
                : snapshot.state === 'starting'
                ? 'STARTING'
                : snapshot.state === 'stopping'
                ? 'STOPPING'
                : snapshot.state === 'off'
                ? 'NOT FILTERING'
                : 'NEEDS ATTENTION'
            }
            tone={
              snapshot?.state === 'active'
                ? 'success'
                : snapshot?.state === 'failed'
                ? 'error'
                : 'warning'
            }
          />
        </View>
        <View style={local.shield}>
          <StatusIcon
            size={44}
            color={colors.heroAccent}
            strokeWidth={1.6}
            accessible={false}
          />
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
            snapshot?.state === 'stopping'
              ? 'Stopping protection'
              : enabled || uncertain
              ? 'Turn off protection'
              : 'Enable protection'
          }
          onPress={
            enabled || uncertain
              ? () => {
                  void stop();
                }
              : enable
          }
          busy={
            busy ||
            snapshot?.state === 'starting' ||
            snapshot?.state === 'stopping'
          }
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
          <ArrowUpRight size={22} color={colors.primary} accessible={false} />
        </View>
        <Text style={styles.body}>
          Add a block rule, allow a site again, or remove an override. You stay
          in control.
        </Text>
        <Button
          title="Manage site rules"
          icon={ArrowUpRight}
          secondary
          onPress={() => navigation.navigate('Sites')}
        />
      </Card>
      <Card>
        <Badge text="BEFORE YOU VISIT" />
        <Text style={styles.heading}>Take a moment to check.</Text>
        <Text style={styles.body}>
          Look for a reviewed website label, then choose your own rule. Your
          manual protection works independently of the catalog.
        </Text>
        <Button
          title="Check a website"
          icon={ArrowUpRight}
          secondary
          onPress={() => navigation.navigate('Check')}
        />
      </Card>
      <Notice text="A saved Block rule is not proof of a blocked request. Catalog checks do not automatically change your manual rules." />
    </Page>
  );
}
const makeLocal = (colors: ThemeColors) =>
  StyleSheet.create({
    hero: {
      backgroundColor: colors.hero,
      borderRadius: 24,
      padding: 22,
      gap: 18,
    },
    eyebrow: {
      fontSize: 10,
      fontWeight: '700',
      color: colors.heroMuted,
      letterSpacing: 1.5,
    },
    shield: {
      width: 76,
      height: 76,
      borderRadius: 24,
      backgroundColor: colors.heroSurface,
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: 6,
    },
    heroTitle: {
      fontSize: 25,
      lineHeight: 31,
      fontWeight: '700',
      letterSpacing: -0.6,
      color: colors.onHero,
    },
    heroBody: { fontSize: 13, lineHeight: 21, color: colors.heroMuted },
    metric: { fontSize: 28, fontWeight: '700', color: colors.text },
  });
