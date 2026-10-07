import React, { useEffect, useState } from 'react';
import { BackHandler, Linking, Text, TextInput, View } from 'react-native';
import { Network, RefreshCw, Users } from 'lucide-react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useNetworkProtection } from '../state/NetworkProtectionContext';
import { useBetGuard } from '../state/BetGuardContext';
import { useTheme } from '../state/ThemeContext';
import { Badge, Button, Card, Empty, Notice, Page } from '../components/ui';
import { HoldButton } from '../components/HoldButton';
import { BottomSheet } from '../components/BottomSheet';
import { relativeTime } from '../components/ActivityRow';
import { API_BASE_URL } from '../api/config';

export function NetworkProtectionScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Network'>;
}) {
  const { styles, colors, mode } = useTheme();
  const { snapshot, available, busy, error, start, stop, refresh } =
    useNetworkProtection();
  const { snapshot: device, save, busy: ruleBusy } = useBetGuard();
  const [address, setAddress] = useState('');
  const [port, setPort] = useState('8080');
  const [instructions, setInstructions] = useState(false);
  const [devices, setDevices] = useState(false);
  const [diagnostics, setDiagnostics] = useState(false);
  const [dismissed, setDismissed] = useState<number[]>([]);
  const [cancelKey, setCancelKey] = useState(0);
  const running =
    snapshot?.state === 'active' || snapshot?.state === 'degraded';
  const transitioning =
    snapshot?.state === 'starting' || snapshot?.state === 'stopping';
  const uncertain = available && !snapshot && !!error;
  const locked = running || transitioning || busy;
  const chosen = snapshot?.interfaces.some(row => row.address === address)
    ? address
    : snapshot?.interfaces[0]?.address ?? '';
  const validPort =
    /^\d+$/.test(port) && Number(port) >= 1024 && Number(port) <= 65535;
  useEffect(
    () =>
      navigation?.addListener('blur', () => {
        setCancelKey(value => value + 1);
        setInstructions(false);
        setDevices(false);
      }),
    [navigation],
  );
  useEffect(() => {
    if (!navigation) return;
    const listener = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!navigation.isFocused()) return false;
      navigation.navigate('Sites');
      return true;
    });
    return () => listener.remove();
  }, [navigation]);
  const warnings = (device?.history ?? [])
    .filter(
      row =>
        row.kind === 'network_warning' &&
        !dismissed.includes(row.id) &&
        !device?.rules.some(rule => rule.domain === row.domain),
    )
    .slice(0, 8);
  const label = !available
    ? 'Android update required'
    : !snapshot
    ? 'Reading gateway status…'
    : {
        off: 'Network Protection Off',
        starting: 'Starting gateway…',
        active: 'NETWORK ACTIVE',
        degraded: 'Network needs attention',
        stopping: 'Stopping gateway…',
        failed: 'Gateway could not start',
        interrupted: 'Gateway interrupted',
      }[snapshot.state];
  const active = snapshot?.state === 'active';
  return (
    <Page
      title="Network Protection"
      subtitle="Protect other devices through this phone."
    >
      <Badge text="CAPSTONE PROTOTYPE" />
      <Card>
        <Network size={38} color={active ? colors.protected : colors.primary} />
        <Text accessibilityLiveRegion="polite" style={styles.heading}>
          {label}
        </Text>
        <Text style={styles.body}>
          {snapshot?.detail ??
            'Update the Android app to enable the phone-hosted gateway.'}
        </Text>
        {snapshot?.address && running && (
          <>
            <Text style={styles.eyebrow}>GATEWAY HOST</Text>
            <Text selectable style={styles.title}>
              {snapshot.address}
            </Text>
            <Text selectable style={styles.body}>
              Port {snapshot.port}
            </Text>
            <Text style={styles.small}>
              Only devices configured to use this proxy send supported web
              traffic through BetGuard.
            </Text>
          </>
        )}
        {!locked && (
          <>
            <Text style={styles.heading}>1. Prepare the connection</Text>
            <Text style={styles.body}>
              Turn on this phone's hotspot with mobile data, or connect it and
              your clients to the same Wi-Fi. Then refresh the addresses.
            </Text>
            <Button
              title="Open connection settings"
              secondary
              onPress={() => {
                void Linking.sendIntent(
                  'android.settings.WIRELESS_SETTINGS',
                ).catch(() => {
                  void Linking.openSettings();
                });
              }}
            />
            <Button
              title="Refresh gateway addresses"
              icon={RefreshCw}
              secondary
              disabled={!available || busy}
              onPress={() => {
                void refresh();
              }}
            />
            <Text style={styles.heading}>2. Choose this phone's address</Text>
            {!snapshot?.interfaces.length ? (
              <Empty
                title="No usable LAN address"
                body="Turn on the hotspot or connect to Wi-Fi, then refresh. The gateway address will appear here."
              />
            ) : (
              snapshot.interfaces.map(row => (
                <Button
                  key={row.address}
                  title={`${row.address} · ${row.interfaceName}`}
                  selected={chosen === row.address}
                  secondary={chosen !== row.address}
                  onPress={() => setAddress(row.address)}
                />
              ))
            )}
            <Text style={styles.body}>Proxy port</Text>
            <TextInput
              accessibilityLabel="Network proxy port"
              value={port}
              onChangeText={setPort}
              keyboardType="number-pad"
              maxLength={5}
              keyboardAppearance={mode}
              placeholder="8080"
              placeholderTextColor={colors.textMuted}
              style={styles.input}
              editable={!busy}
            />
            {!API_BASE_URL && (
              <Notice text="Network detection needs a configured BetGuard service. Use the USB development app for the local server, or configure a reachable HTTPS service for the saved APK." />
            )}
            <Button
              title="Start Network Protection"
              icon={Network}
              busy={busy}
              disabled={
                !available ||
                !snapshot ||
                !chosen ||
                !validPort ||
                !API_BASE_URL
              }
              onPress={() => {
                setInstructions(true);
                void start(chosen, Number(port));
              }}
            />
          </>
        )}
        {(running || uncertain) && (
          <HoldButton
            title="Hold to stop Network Protection"
            cancelKey={cancelKey}
            disabled={busy || transitioning}
            confirmationTitle="Stop Network Protection?"
            confirmationAction="Stop network"
            confirmationMessage="Clients using this proxy will lose access through it. Set their Wi-Fi proxy to None to browse directly. Saved rules stay on this phone."
            onComplete={() => {
              void stop();
            }}
          />
        )}
        {transitioning && (
          <Text style={styles.small}>
            Please wait for the gateway to finish this action.
          </Text>
        )}
        {error && <Notice text={error} tone="error" />}
      </Card>
      <Card>
        <View style={styles.spread}>
          <Text style={styles.body}>Protected devices</Text>
          <Text style={styles.heading}>{snapshot?.clients.length ?? '—'}</Text>
        </View>
        <View style={styles.spread}>
          <Text style={styles.body}>Blocked this session</Text>
          <Text style={styles.heading}>{snapshot?.blocked ?? '—'}</Text>
        </View>
        <View style={styles.spread}>
          <Text style={styles.body}>Warnings this session</Text>
          <Text style={styles.heading}>{snapshot?.warnings ?? '—'}</Text>
        </View>
        <Text style={styles.small}>
          Counts are actual proxy requests. Clients remain listed while a
          connection is open or for two minutes after their last request.
        </Text>
        <Button
          title="View devices"
          icon={Users}
          secondary
          onPress={() => setDevices(true)}
        />
        <Button
          title="Connection instructions"
          secondary
          onPress={() => setInstructions(true)}
        />
        <Button
          title="View network activity"
          secondary
          onPress={() => navigation?.navigate('History')}
        />
      </Card>
      <Text style={styles.heading}>Network Review</Text>
      {!warnings.length ? (
        <Empty
          title="No pending reviews"
          body="Model warnings appear here after a client makes a supported request. Warnings keep access allowed."
        />
      ) : (
        warnings.map(row => (
          <Card key={row.id}>
            <Badge text="REVIEW · ALLOWED" tone="warning" />
            <Text selectable style={styles.heading}>
              {row.domain}
            </Text>
            <Text selectable style={styles.body}>
              Device: {row.clientIp ?? 'Unavailable'}
            </Text>
            <Text style={styles.small}>
              Uncertain model warning · {relativeTime(row.createdAt)}. This does
              not establish that the site is gambling.
            </Text>
            <View style={styles.wrap}>
              <Button
                title="Block Site"
                disabled={ruleBusy}
                onPress={() => {
                  void save(row.domain, 'block', false);
                }}
              />
              <Button
                title="Always Allow"
                secondary
                disabled={ruleBusy}
                onPress={() => {
                  void save(row.domain, 'allow', false);
                }}
              />
              <Button
                title="Dismiss"
                secondary
                onPress={() =>
                  setDismissed(values => [...values, row.id].slice(-200))
                }
              />
            </View>
            <Text style={styles.small}>
              Saved choices use the same website rules for Device and Network
              Protection. Blocking also closes active proxy tunnels for this
              hostname.
            </Text>
          </Card>
        ))
      )}
      <Button
        title={diagnostics ? 'Hide demo diagnostics' : 'Demo Diagnostics'}
        secondary
        onPress={() => setDiagnostics(value => !value)}
      />
      {diagnostics && (
        <Card>
          <Text style={styles.heading}>Gateway diagnostics</Text>
          <Text selectable style={styles.small}>
            Gateway:{' '}
            {snapshot?.address && running
              ? `${snapshot.address}:${snapshot.port}`
              : 'Not listening'}
            {'\n'}
            Decision service:{' '}
            {snapshot?.runtime === 'ready'
              ? 'Responded to a request'
              : snapshot?.runtime === 'unavailable'
              ? 'Unavailable'
              : 'Not checked yet'}
            {'\n'}
            Requests: {snapshot?.requests ?? 0} · Allowed:{' '}
            {snapshot?.allowed ?? 0}
            {'\n'}
            Blocked: {snapshot?.blocked ?? 0} · Warnings:{' '}
            {snapshot?.warnings ?? 0}
            {'\n'}
            Request errors: {snapshot?.errors ?? 0} · Rejected
            connections/requests: {snapshot?.rejected ?? 0}
          </Text>
          <Text style={styles.small}>
            Warnings are included in Allowed. Session counters reset when the
            gateway starts. The existing server loads its model and list once
            per process.
          </Text>
        </Card>
      )}
      <Text style={styles.small}>
        This prototype filters HTTP and HTTPS traffic from applications that
        honor manual proxy settings. HTTPS stays encrypted. Direct traffic and
        proxy-ignoring apps bypass it. Keep this phone connected and the gateway
        running; set clients' proxy to None when the demonstration ends.
      </Text>
      <BottomSheet
        visible={instructions}
        title="Connect a protected device"
        onClose={() => setInstructions(false)}
      >
        <Text style={styles.body}>
          1. Turn on this phone's hotspot and connect the client, or connect
          both devices to the same home Wi-Fi.
        </Text>
        <Text style={styles.body}>
          2. Start Network Protection, then open the client's Wi-Fi proxy
          settings and choose Manual.
        </Text>
        <Text selectable style={styles.heading}>
          Host:{' '}
          {running && snapshot?.address
            ? snapshot.address
            : 'Shown after the gateway starts'}
          {'\n'}Port:{' '}
          {running ? snapshot?.port : 'Shown after the gateway starts'}
        </Text>
        <Text style={styles.body}>
          3. Enter this host and port, save, then open a website. The client
          appears after a request reaches BetGuard.
        </Text>
        <Text style={styles.body}>
          4. Test wikipedia.org (Allow), stake.com (Block), and microsoft.com
          (current model WARN). Confirm the client's IP and decision in
          Activity.
        </Text>
        <Notice text="When finished, set the client's Wi-Fi proxy to None/Off. Joining the hotspot alone does not enable BetGuard filtering." />
      </BottomSheet>
      <BottomSheet
        visible={devices}
        title="Protected devices"
        onClose={() => setDevices(false)}
      >
        {!snapshot?.clients.length ? (
          <Empty
            title="No protected clients yet"
            body="Connect a client using the displayed manual proxy, then open a website."
          />
        ) : (
          snapshot.clients.map(client => (
            <Card key={client.ip}>
              <Text selectable style={styles.heading}>
                {client.ip}
              </Text>
              <Text style={styles.body}>
                {client.connections > 0
                  ? `${client.connections} active connections`
                  : `Last activity ${relativeTime(client.lastActivity)}`}
              </Text>
              <Text style={styles.small}>
                First seen {new Date(client.firstSeen).toLocaleTimeString()}
                {'\n'}Last activity{' '}
                {new Date(client.lastActivity).toLocaleTimeString()}
                {'\n'}
                Requests: {client.requests} · Blocked: {client.blocked} ·
                Warnings: {client.warnings}
              </Text>
            </Card>
          ))
        )}
      </BottomSheet>
    </Page>
  );
}
