import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '../state/ThemeContext';
import { Button, Card } from './ui';
import { useNetworkProtection } from '../state/NetworkProtectionContext';

export function HowItWorks() {
  const { styles } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const { snapshot: network } = useNetworkProtection();
  return (
    <Card>
      <Button
        title={expanded ? 'Close quick guide' : 'How BetGuard works'}
        secondary
        selected={expanded}
        onPress={() => setExpanded(!expanded)}
      />
      {expanded && (
        <View style={styles.stack}>
          <Text style={styles.heading}>A safer study environment</Text>
          <Text style={styles.body}>
            BetGuard helps students reduce access to gambling websites and
            supported gambling connections from apps. It restricts network
            requests; it does not uninstall apps or prevent them from opening.
          </Text>
          <Text style={styles.heading}>1. Choose your protection</Text>
          <Text style={styles.body}>
            On-device rules use your saved Block and Allow choices. They work
            without BetGuard’s server. Smart protection adds online blocklist
            and AI checks for websites with no matching rule.
          </Text>
          <Text style={styles.heading}>
            2. Start, then approve Android’s request
          </Text>
          <Text style={styles.body}>
            BetGuard uses Android’s VPN permission to filter supported website
            address requests on this phone. It is not a VPN that hides your
            location. Wait for ON before browsing. Only one VPN can run at a
            time.
          </Text>
          <Text style={styles.heading}>3. Browse and review Activity</Text>
          <Text style={styles.body}>
            Your matching rules come first. Block stops a supported request;
            Review suggests caution and keeps access allowed; Allow lets the
            request continue. Activity shows requests handled by protection.
            After adding a block, restart your browser and reload the page. A
            restored tab can show an old page even when new requests are
            blocked.
          </Text>
          <Text style={styles.heading}>
            Checking is separate from protecting
          </Text>
          <Text style={styles.body}>
            Check link reads your local rule and, when available, asks the
            online detector for advice. A check does not turn protection on or
            save a rule. Use Block site or Always allow to save your choice.
          </Text>
          <Text style={styles.heading}>What does offline mean?</Text>
          <Text style={styles.body}>
            Rules and activity stay on your phone. On-device rules need no
            BetGuard server, but browsing websites still needs internet. The AI
            model runs on the server, not in this APK. Smart protection needs
            both internet and a reachable BetGuard service.
          </Text>
          <Text style={styles.heading}>Review an app separately</Text>
          <Text style={styles.body}>
            Open Protection, then Review an app. Choose a visible app with your
            permission, add its public description or reviews, and agree before
            sending that information. This uses a separate app metadata model
            when available. The existing website model checks hostnames, not app
            descriptions.
          </Text>
          <Text style={styles.heading}>Device and Network Protection</Text>
          <Text style={styles.body}>
            Home's Device Protection filters supported DNS on this phone.
            Network Protection runs a separate phone-hosted proxy for other
            devices. Both use the same saved rules and existing online detector.
            The model stays on the FastAPI server; HTTPS traffic stays
            encrypted.
          </Text>
          <Text style={styles.small}>
            Client → phone proxy → your rules → verified list → model → Allow /
            Review / Block → internet.
          </Text>
          <Text style={styles.heading}>
            Protect devices through your hotspot
          </Text>
          <Text style={styles.body}>
            Turn on this phone's hotspot and mobile data. Open Protection →
            Network Protection, refresh the addresses and start the gateway.
            Connect the client to the hotspot. In its Wi-Fi settings choose
            Manual Proxy and enter the host and port shown by BetGuard. Save and
            browse. Joining the hotspot alone does not enable filtering.
          </Text>
          <Text style={styles.heading}>Protect devices on home Wi-Fi</Text>
          <Text style={styles.body}>
            Connect this phone and the client to the same router. Start Network
            Protection using this phone's Wi-Fi address, then set that address
            and port as the client's manual proxy. Confirm its requests in
            Activity. BetGuard does not change your router's settings.
          </Text>
          {network?.address &&
            ['active', 'degraded'].includes(network.state) && (
              <Text selectable style={styles.body}>
                Current proxy host: {network.address}
                {'\n'}Port: {network.port}
              </Text>
            )}
          <Text style={styles.small}>
            Network Protection is a small-network demonstration prototype. Only
            apps that use the proxy are covered. Keep the gateway phone and
            backend reachable. When finished, set each client's proxy to
            None/Off. Dedicated gateway hardware is a future deployment option.
          </Text>
          <Text style={styles.small}>
            Protection covers supported DNS requests. Encrypted DNS, cached
            answers and existing connections can bypass it. Re-enable protection
            after restarting the phone or terminating the app. If the smart
            service fails, requests can fail too; stop protection and choose
            On-device rules to use your saved choices without that service.
          </Text>
        </View>
      )}
    </Card>
  );
}
