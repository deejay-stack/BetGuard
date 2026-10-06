import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import {
  Shield,
  Wifi,
  Smartphone,
  ListFilter,
  Activity,
  Search,
} from 'lucide-react-native';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Button, Card, Empty, Loading, Page } from '../components/ui';
import { ActivityRow, activityKind } from '../components/ActivityRow';
import { HowItWorks } from '../components/HowItWorks';
import { HoldButton } from '../components/HoldButton';
import { ProtectionRing } from '../components/ProtectionRing';
import { SecurityCard } from '../components/SecurityCard';
import { BottomSheet } from '../components/BottomSheet';
import { useTheme } from '../state/ThemeContext';
import { API_BASE_URL } from '../api/config';

export function HomeScreen({ navigation }: BottomTabScreenProps<Tabs, 'Home'>) {
  const { colors, styles } = useTheme();
  const { snapshot, available, busy, error, start, stop } = useBetGuard();
  const [online, setOnline] = useState(false);
  const [intro, setIntro] = useState(false);
  const [explained, setExplained] = useState(false);
  const [dnsDetails, setDnsDetails] = useState(false);
  const [holdRevision, setHoldRevision] = useState(0);
  const active = snapshot?.state === 'active';
  const enabled = active || snapshot?.state === 'degraded';
  const transition =
    snapshot?.state === 'starting' || snapshot?.state === 'stopping';
  const uncertain = available && !snapshot && !!error;
  const selectedOnline =
    enabled || transition ? !!snapshot?.detectionEnabled : online;
  const locked = enabled || transition || busy;
  useEffect(() => {
    if (enabled) setOnline(!!snapshot?.detectionEnabled);
  }, [enabled, snapshot?.detectionEnabled]);
  useEffect(
    () =>
      navigation.addListener?.('blur', () => {
        setHoldRevision(value => value + 1);
        setIntro(false);
        setDnsDetails(false);
      }),
    [navigation],
  );
  const history = snapshot?.history ?? [];
  const recent = history
    .filter(event => event.kind.startsWith('dns_'))
    .slice(0, 3);
  const latestBlock = history.find(
    event => activityKind(event.kind) === 'Blocked',
  )?.id;
  const today = new Date().setHours(0, 0, 0, 0);
  const blocked = history.filter(
    event => event.createdAt >= today && activityKind(event.kind) === 'Blocked',
  ).length;
  const warnings = history.filter(
    event =>
      event.createdAt >= today && activityKind(event.kind) === 'Warnings',
  ).length;
  const needsAttention =
    snapshot?.state === 'degraded' || snapshot?.state === 'interrupted';
  const tone = active
    ? 'success'
    : needsAttention
    ? 'warning'
    : snapshot?.state === 'failed'
    ? 'error'
    : 'inactive';
  const label = !snapshot
    ? available
      ? 'Reading status…'
      : 'Android build required'
    : {
        active: 'Protected',
        off: 'Protection Off',
        starting: 'Starting…',
        stopping: 'Pausing…',
        degraded: 'Attention Required',
        interrupted: 'Protection Interrupted',
        failed: 'Protection Error',
      }[snapshot.state];
  function enable() {
    if (!explained) setIntro(true);
    else void start(online);
  }
  return (
    <Page
      title="Your security, at a glance."
      subtitle="Stay in control of where you browse."
    >
      <Card>
        <ProtectionRing state={snapshot?.state} blockedEvent={latestBlock} />
        <View style={local.center}>
          <Text
            accessibilityLiveRegion="polite"
            style={[
              styles.title,
              local.centerText,
              {
                color: active
                  ? colors.protected
                  : needsAttention
                  ? colors.warning
                  : colors.text,
              },
            ]}
          >
            {label}
          </Text>
          <View>
            <Badge
              text={
                active
                  ? 'DNS FILTER ACTIVE'
                  : transition
                  ? 'PLEASE WAIT'
                  : needsAttention
                  ? 'CHECK CONNECTION'
                  : snapshot?.state === 'off'
                  ? 'FILTER INACTIVE'
                  : 'NOT CONFIRMED ACTIVE'
              }
              tone={tone}
            />
          </View>
          <Text style={[styles.body, local.centerText]}>
            {active
              ? `BetGuard is filtering supported domain requests using ${
                  selectedOnline
                    ? 'your rules and smart detection'
                    : 'your saved rules'
                }.`
              : snapshot && snapshot.state !== 'off'
              ? snapshot.detail
              : 'Choose how to protect your browsing, then enable the filter.'}
          </Text>
        </View>
        {!enabled && !transition && (
          <>
            <Text style={styles.eyebrow}>PROTECTION MODE</Text>
            <View style={local.grid}>
              {[false, true].map(smart => {
                const disabled = locked || (smart && !API_BASE_URL);
                const selected = selectedOnline === smart;
                const Icon = smart ? Wifi : Smartphone;
                return (
                  <Pressable
                    key={String(smart)}
                    accessibilityRole="radio"
                    accessibilityLabel={
                      smart ? 'Smart protection' : 'On-device rules'
                    }
                    accessibilityState={{ checked: selected, disabled }}
                    disabled={disabled}
                    onPress={() => setOnline(smart)}
                    style={[
                      local.mode,
                      {
                        backgroundColor: selected
                          ? colors.primarySoft
                          : colors.input,
                        borderColor: selected ? colors.primary : colors.border,
                      },
                      disabled && styles.modeDisabled,
                    ]}
                  >
                    <View style={styles.spread}>
                      <Icon
                        size={20}
                        color={selected ? colors.primary : colors.textMuted}
                      />
                      <View
                        style={[
                          local.radio,
                          {
                            borderColor: selected
                              ? colors.primary
                              : colors.border,
                            backgroundColor: selected
                              ? colors.primary
                              : colors.surface,
                          },
                        ]}
                      />
                    </View>
                    <View>
                      <Text style={styles.body}>
                        {smart ? 'Smart protection' : 'On-device rules'}
                      </Text>
                      <Text style={styles.small}>
                        {smart
                          ? 'Rules + online checks'
                          : 'Rules on this phone'}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>
            {!API_BASE_URL && (
              <Text style={styles.small}>
                Smart protection needs a configured online service. Your saved
                rules are ready to use.
              </Text>
            )}
          </>
        )}
        {enabled || uncertain ? (
          <HoldButton
            disabled={busy || transition}
            cancelKey={holdRevision}
            onComplete={() => {
              void stop();
            }}
          />
        ) : (
          <Button
            title={transition ? 'Please wait' : 'Enable protection'}
            icon={Shield}
            busy={busy || transition}
            disabled={!available || !snapshot}
            onPress={enable}
          />
        )}
        {enabled && (
          <Text style={[styles.small, local.centerText]}>
            Stop protection to change modes. Your rules stay saved.
          </Text>
        )}
      </Card>
      {!snapshot && available && <Loading />}
      <Button
        title="Check a link"
        icon={Search}
        onPress={() => navigation.navigate('Check')}
      />
      <View style={styles.spread}>
        <Text style={styles.heading}>What protects you</Text>
        <Badge text={selectedOnline ? 'SMART MODE' : 'LOCAL MODE'} />
      </View>
      <View style={local.grid}>
        <SecurityCard
          title="DNS protection"
          icon={Shield}
          value={
            active
              ? 'ACTIVE'
              : needsAttention
              ? 'WARNING'
              : snapshot?.state === 'failed'
              ? 'ERROR'
              : 'INACTIVE'
          }
          tone={tone}
          detail="Filters supported requests before sites load."
          onPress={() => setDnsDetails(true)}
        />
        <SecurityCard
          title="Website rules"
          icon={ListFilter}
          value={`${snapshot?.rules.length ?? 0} SAVED`}
          detail={`${
            snapshot?.rules.filter(rule => rule.action === 'block').length ?? 0
          } block · ${
            snapshot?.rules.filter(rule => rule.action === 'allow').length ?? 0
          } allow`}
          onPress={() => navigation.navigate('Sites')}
        />
        <SecurityCard
          title="Smart detection"
          icon={Wifi}
          value={
            !API_BASE_URL
              ? 'NOT SET UP'
              : active && selectedOnline
              ? 'ACTIVE'
              : enabled && selectedOnline
              ? 'WARNING'
              : 'INACTIVE'
          }
          tone={enabled && selectedOnline ? tone : 'primary'}
          detail={
            !API_BASE_URL
              ? 'On-device rules remain available.'
              : selectedOnline && enabled
              ? 'Verified blocklist + automated advice.'
              : 'Select Smart mode to use online checks.'
          }
          onPress={() => setDnsDetails(true)}
        />
        <SecurityCard
          title="Activity"
          icon={Activity}
          value={`${
            history.filter(event => event.kind.startsWith('dns_')).length
          } REQUESTS`}
          detail="Review recent filtering outcomes."
          onPress={() => navigation.navigate('History')}
        />
      </View>
      <View style={[styles.card, styles.row]}>
        <View style={styles.flex}>
          <Text style={styles.small}>Blocked today</Text>
          <Text style={[styles.title, { color: colors.blocked }]}>
            {blocked}
          </Text>
        </View>
        <View style={styles.flex}>
          <Text style={styles.small}>Reviews today</Text>
          <Text style={[styles.title, { color: colors.review }]}>
            {warnings}
          </Text>
        </View>
      </View>
      <Text style={styles.small}>
        Request counts use the latest 200 saved events, so totals may be
        incomplete. Reviews stay allowed.
      </Text>
      {snapshot?.state === 'off' &&
        snapshot.rules.length === 0 &&
        !selectedOnline && (
          <Card>
            <Text style={styles.heading}>Start with your first rule</Text>
            <Text style={styles.body}>
              On-device protection blocks the websites you choose. Add a rule
              before you browse.
            </Text>
            <Button
              title="Add a website rule"
              secondary
              onPress={() => navigation.navigate('Sites')}
            />
          </Card>
        )}
      <View style={styles.spread}>
        <Text style={styles.heading}>Recent activity</Text>
        <Button
          title="View activity"
          secondary
          onPress={() => navigation.navigate('History')}
        />
      </View>
      {!recent.length ? (
        <Empty
          title="Your activity starts here"
          body="Enable protection, then browse. Actual filtering outcomes will appear here."
        />
      ) : (
        recent.map(item => <ActivityRow key={item.id} item={item} />)
      )}
      <HowItWorks />
      <BottomSheet
        visible={intro}
        title="Enable network protection"
        onClose={() => setIntro(false)}
      >
        <Text style={styles.heading}>Why Android asks for VPN permission</Text>
        <Text style={styles.body}>
          BetGuard creates a local DNS filter to apply your website rules.
          Android uses its VPN permission to let this filter handle supported
          domain requests.
        </Text>
        <Text style={styles.body}>
          This filter checks hostnames. It does not inspect webpage content,
          passwords, or private messages, and it does not hide your location.
        </Text>
        <Text style={styles.small}>
          {online
            ? 'Unmatched hostnames are sent to your BetGuard server for smart detection.'
            : 'Your rules are checked on this phone. Allowed requests use an external DNS resolver.'}{' '}
          Browsing still needs internet.
        </Text>
        <Button
          title="Continue to Android permission"
          disabled={busy}
          onPress={() => {
            setIntro(false);
            setExplained(true);
            void start(online);
          }}
        />
      </BottomSheet>
      <BottomSheet
        visible={dnsDetails}
        title="DNS protection"
        onClose={() => setDnsDetails(false)}
      >
        <Badge
          text={
            active
              ? 'ACTIVE'
              : needsAttention
              ? 'ATTENTION REQUIRED'
              : 'NOT CONFIRMED ACTIVE'
          }
          tone={tone}
        />
        <Text style={styles.body}>
          Your matching Block or Allow rule comes first. Smart mode checks
          unmatched hostnames against the server's verified blocklist and
          trained detector. Review warnings keep access allowed.
        </Text>
        <Text style={styles.small}>
          Provider: Cloudflare (1.1.1.1). The app uses ordinary DNS.
          Encrypted/private DNS, cached addresses and unsupported DNS paths can
          bypass this filter.
        </Text>
        <Button
          title="Manage website rules"
          secondary
          onPress={() => {
            setDnsDetails(false);
            navigation.navigate('Sites');
          }}
        />
        <Button
          title="Close DNS details"
          secondary
          onPress={() => setDnsDetails(false)}
        />
      </BottomSheet>
    </Page>
  );
}
const local = StyleSheet.create({
  center: { alignItems: 'center', gap: 12 },
  centerText: { textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  radio: { width: 16, height: 16, borderRadius: 8, borderWidth: 2 },
  mode: {
    flexGrow: 1,
    flexBasis: '45%',
    minWidth: 130,
    borderWidth: 1,
    borderRadius: 16,
    padding: 12,
    gap: 8,
  },
});
