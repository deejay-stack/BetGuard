import React, { useEffect, useState } from 'react';
import { AppState, Text, TextInput, View } from 'react-native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../../App';
import { useRouterProtection } from '../state/RouterProtectionContext';
import { useBetGuard } from '../state/BetGuardContext';
import { useTheme } from '../state/ThemeContext';
import { Badge, Button, Card, Empty, Notice, Page } from '../components/ui';
import { HoldButton } from '../components/HoldButton';
import { BottomSheet } from '../components/BottomSheet';
import { relativeTime } from '../components/ActivityRow';
import { API_BASE_URL } from '../api/config';

export function RouterProtectionScreen({
  navigation,
}: {
  navigation?: BottomTabNavigationProp<Tabs, 'Router'>;
}) {
  const router = useRouterProtection();
  const { save, busy: ruleBusy, snapshot: phone } = useBetGuard();
  const { styles, mode, colors } = useTheme();
  const [serviceKey, setServiceKey] = useState('');
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('root');
  const [password, setPassword] = useState('');
  const [authorized, setAuthorized] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [devices, setDevices] = useState(false);
  const [details, setDetails] = useState(false);
  const [dismissed, setDismissed] = useState<number[]>([]);
  const [cancelKey, setCancelKey] = useState(0);
  useEffect(() => {
    const listener = AppState.addEventListener('change', state => {
      if (state !== 'active') setPassword('');
    });
    const blur = navigation?.addListener('blur', () => {
      setPassword('');
      setServiceKey('');
      setConfirmed(false);
      setCancelKey(n => n + 1);
    });
    return () => {
      listener.remove();
      blur?.();
    };
  }, [navigation]);
  const status = router?.snapshot;
  const active =
    status?.state === 'active' && router?.rulesSynced && !router.error;
  const unfinished = status && !['off', 'preview'].includes(status.state);
  const warnings =
    status?.history
      .filter(
        e =>
          e.kind === 'router_warning' &&
          !dismissed.includes(e.id) &&
          !phone?.rules.some(
            rule =>
              rule.domain === e.domain ||
              (rule.includeSubdomains && e.domain.endsWith('.' + rule.domain)),
          ),
      )
      .slice(0, 8) ?? [];
  const input = {
    style: styles.input,
    keyboardAppearance: mode,
    placeholderTextColor: colors.textMuted,
    autoCapitalize: 'none' as const,
    autoCorrect: false,
  };
  return (
    <Page
      title="Router Protection"
      subtitle="Automatic DNS filtering for an authorized OpenWrt network."
    >
      <Badge text="OPENWRT PROTOTYPE" />
      {!API_BASE_URL && (
        <Notice text="Router Protection needs a reachable BetGuard API. Use the USB development app for the local server, or configure a public HTTPS API address before building the standalone APK." />
      )}
      <Card>
        <Text style={styles.heading}>
          {active
            ? 'NETWORK ACTIVE'
            : status?.state === 'offline'
            ? 'ROUTER OFFLINE'
            : status?.state === 'degraded' || status?.state === 'active'
            ? 'NETWORK DEGRADED'
            : status?.state === 'recovery_required'
            ? 'Router recovery required'
            : status?.state === 'applying'
            ? 'Verifying router protection…'
            : status?.state === 'restoring'
            ? 'Restoring previous settings…'
            : status?.state === 'preview'
            ? 'Review configuration'
            : router?.connected && !status
            ? 'Filtering service unavailable'
            : 'Not configured'}
        </Text>
        <Text style={styles.body}>
          {status?.detail ??
            'This mode needs a compatible OpenWrt router and a dedicated BetGuard DNS service on its LAN.'}
        </Text>
        <Text style={styles.small}>
          Clients join Wi-Fi normally. No BetGuard installation or manual proxy
          is needed for conventional DNS filtering.
        </Text>
        {router?.error && <Notice tone="error" text={router.error} />}
        {router?.connected && !router.rulesSynced && (
          <Notice text="Phone rule synchronization is not confirmed. Refresh the service before assuming recent rules apply to router clients." />
        )}
      </Card>
      {!router?.connected || !status ? (
        <Card>
          <Text style={styles.heading}>1. Connect the filtering service</Text>
          <Text style={styles.body}>
            Enter the administrator token created on your BetGuard server. It
            stays in session memory. This is separate from the router password.
          </Text>
          <TextInput
            {...input}
            accessibilityLabel="Router service administrator token"
            secureTextEntry
            value={serviceKey}
            onChangeText={setServiceKey}
            maxLength={256}
          />
          <Button
            title="Connect filtering service"
            disabled={
              !API_BASE_URL || serviceKey.trim().length < 32 || router?.busy
            }
            onPress={() => {
              const key = serviceKey;
              setServiceKey('');
              void router?.unlock(key);
            }}
          />
        </Card>
      ) : (
        <>
          <Card>
            <Text style={styles.heading}>Router details</Text>
            <Text selectable style={styles.body}>
              Router: {status.router ?? 'Enter its address below'}
              {'\n'}Platform: {status.routerType ?? 'Not checked'}
              {status.version ? ` ${status.version}` : ''}
              {'\n'}DNS filter: {status.filterHost}:{status.filterPort}
            </Text>
            <Text style={styles.small}>
              DNS service: {status.dnsRunning ? 'Listening' : 'Unavailable'}
              {'\n'}ML runtime: {status.mlReady ? 'Ready' : 'Unavailable'}
              {'\n'}Verified blocklist:{' '}
              {status.blocklistLoaded ? 'Loaded' : 'Unavailable'}
              {'\n'}DNS enforcement:{' '}
              {status.enforcementVerified && active
                ? 'Verified'
                : 'Not currently verified'}
            </Text>
            <Button
              title="Refresh router status"
              secondary
              onPress={() => {
                void router.refresh();
                void router.sync().catch(() => {});
              }}
            />
            {unfinished && (
              <Button
                title="Verify router protection"
                secondary
                disabled={router.busy}
                onPress={() => {
                  void router.verify();
                }}
              />
            )}
          </Card>
          {!active && (
            <Card>
              <Text style={styles.heading}>
                {unfinished
                  ? 'Reconnect for recovery'
                  : '2. Authenticate to OpenWrt'}
              </Text>
              <Notice text="Router Protection changes network settings for devices using this router. Only continue if you own or administer this network." />
              <Button
                title={
                  authorized
                    ? 'Network administration authorization confirmed'
                    : 'I own or administer this network'
                }
                secondary
                selected={authorized}
                onPress={() => setAuthorized(v => !v)}
              />
              <Text style={styles.body}>Router HTTPS address</Text>
              <TextInput
                {...input}
                accessibilityLabel="OpenWrt router HTTPS address"
                placeholder="Enter the actual HTTPS router address"
                value={url}
                onChangeText={setUrl}
                maxLength={200}
                keyboardType="url"
              />
              <Text style={styles.body}>Administrator username</Text>
              <TextInput
                {...input}
                accessibilityLabel="OpenWrt administrator username"
                value={username}
                onChangeText={setUsername}
                maxLength={64}
              />
              <Text style={styles.body}>Administrator password</Text>
              <TextInput
                {...input}
                accessibilityLabel="OpenWrt administrator password"
                secureTextEntry
                value={password}
                onChangeText={setPassword}
                maxLength={256}
              />
              <Button
                title="Connect securely and preview"
                busy={router.busy}
                disabled={
                  !authorized ||
                  !url.startsWith('https://') ||
                  !username ||
                  !password
                }
                onPress={() => {
                  const secret = password;
                  setPassword('');
                  setConfirmed(false);
                  void router.connect(url, username, secret, authorized);
                }}
              />
              <Text style={styles.small}>
                HTTPS certificate validation is required. Ask the router
                administrator to prepare trusted HTTPS and ubus access. An ISP
                router is unsupported until compatibility is verified.
              </Text>
            </Card>
          )}
          {status.state === 'preview' && (
            <Card>
              <Text style={styles.heading}>3. Review the proposed changes</Text>
              <Text style={styles.body}>
                Send DNS to {status.filterHost}:{status.filterPort}; advertise
                the router as LAN DNS; redirect LAN TCP/UDP port 53 to its DNS
                forwarder.
              </Text>
              {status.changes.map(change => (
                <Text
                  selectable
                  style={styles.small}
                  key={`${change.section}.${change.option}`}
                >
                  {change.config}.{change.section}.{change.option}
                  {'\n'}Before: {JSON.stringify(change.before) ?? 'Unset'}
                  {'\n'}After: {JSON.stringify(change.after)}
                </Text>
              ))}
              <Text selectable style={styles.small}>
                New firewall entry: {JSON.stringify(status.firewallRule)}
              </Text>
              <Text style={styles.small}>
                Original changed values are saved for restoration. Wi-Fi
                credentials, LAN/WAN addressing and unrelated firewall entries
                stay outside this configuration.
              </Text>
              <Button
                title={
                  confirmed
                    ? 'Configuration changes approved'
                    : 'I approve these DNS configuration changes'
                }
                selected={confirmed}
                secondary
                onPress={() => setConfirmed(v => !v)}
              />
              <Button
                title="Apply Router Protection"
                disabled={
                  !authorized ||
                  !confirmed ||
                  !router.rulesSynced ||
                  router.busy
                }
                busy={router.busy}
                onPress={() => {
                  setConfirmed(false);
                  void router.apply();
                }}
              />
            </Card>
          )}
          {unfinished && (
            <Card>
              <Text style={styles.heading}>
                {status.clients.length} requesting clients
              </Text>
              <Text style={styles.body}>
                Requests: {status.requests} · Allowed: {status.allowed}
                {'\n'}Blocked: {status.blocked} · Warnings: {status.warnings} ·
                Errors: {status.errors}
              </Text>
              <Text style={styles.small}>
                Warnings remain allowed. Clients appear after DNS requests reach
                the filter; this is not a count of all Wi-Fi stations. Counters
                cover this session, not a full day.
              </Text>
              <Button
                title="View router devices"
                secondary
                onPress={() => setDevices(true)}
              />
              <Button
                title="View router activity"
                secondary
                onPress={() => navigation?.navigate('History')}
              />
              <Button
                title="Manage shared rules"
                secondary
                onPress={() => navigation?.navigate('Sites')}
              />
              <HoldButton
                title="Hold to stop Router Protection"
                cancelKey={cancelKey}
                disabled={router.busy}
                confirmationTitle="Restore router settings?"
                confirmationAction="Restore and stop"
                confirmationMessage="Restore the saved DNS/DHCP settings and remove only BetGuard’s firewall rule. Protection is off only after restoration is verified."
                onComplete={() => {
                  void router.stop();
                }}
              />
            </Card>
          )}
          <Text style={styles.heading}>Network Review</Text>
          {!warnings.length ? (
            <Empty
              title="No router reviews"
              body="Warning DNS requests remain allowed and appear here for administrator review."
            />
          ) : (
            warnings.map(event => (
              <Card key={event.id}>
                <Badge text="REVIEW · ALLOWED" tone="warning" />
                <Text selectable style={styles.heading}>
                  {event.domain}
                </Text>
                <Text selectable style={styles.body}>
                  Device: {event.clientIp} · {relativeTime(event.createdAt)}
                </Text>
                <Text style={styles.small}>
                  Automated model warning; this does not establish that the site
                  is gambling.
                </Text>
                <View style={styles.wrap}>
                  <Button
                    title="Block Site"
                    disabled={ruleBusy || router.busy}
                    onPress={() => {
                      void save(event.domain, 'block', false)
                        .then(host => {
                          if (host) return router.sync();
                        })
                        .catch(() => {});
                    }}
                  />
                  <Button
                    title="Always Allow"
                    secondary
                    disabled={ruleBusy || router.busy}
                    onPress={() => {
                      void save(event.domain, 'allow', false)
                        .then(host => {
                          if (host) return router.sync();
                        })
                        .catch(() => {});
                    }}
                  />
                  <Button
                    title="Dismiss"
                    secondary
                    onPress={() => setDismissed(ids => [...ids, event.id])}
                  />
                </View>
                <Text style={styles.small}>
                  Updates the phone's existing saved rules and synchronizes them
                  to this filter. Cached client DNS and existing connections may
                  persist briefly.
                </Text>
              </Card>
            ))
          )}
          <Button
            title="Router diagnostics and setup"
            secondary
            onPress={() => setDetails(v => !v)}
          />
          {details && (
            <Card>
              <Text style={styles.body}>
                1. Prepare a compatible, authorized OpenWrt LAN and a stable
                BetGuard server address.{'\n'}2. Connect this administrator
                phone and authenticate securely.{'\n'}3. Review and approve the
                preview.{'\n'}4. Wait for verified Network Active.{'\n'}5.
                Connect clients normally, with proxy off, and test fresh
                requests.{'\n'}6. Hold Stop to restore the previous router
                settings before shutting down the server.
              </Text>
            </Card>
          )}
        </>
      )}
      <Notice text="Small-network capstone prototype. Conventional DNS on TCP/UDP 53 is supported. DoH, DoT, VPNs, alternative networks, cached answers and existing connections can bypass domain filtering. Keep the dedicated DNS server available." />
      <Button
        title="Open Hotspot Protection"
        secondary
        onPress={() => navigation?.navigate('Network')}
      />
      <BottomSheet
        visible={devices}
        title="Router devices"
        onClose={() => setDevices(false)}
      >
        {status?.clients.map(client => (
          <Card key={client.ip}>
            <Text selectable style={styles.heading}>
              {client.ip}
            </Text>
            <Text style={styles.body}>
              First seen: {new Date(client.firstSeen).toLocaleTimeString()}
              {'\n'}Last activity: {relativeTime(client.lastActivity)}
              {'\n'}Requests: {client.requests} · Blocked: {client.blocked} ·
              Warnings: {client.warnings}
            </Text>
          </Card>
        ))}
      </BottomSheet>
    </Page>
  );
}
