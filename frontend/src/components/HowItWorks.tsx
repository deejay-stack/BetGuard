import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '../state/ThemeContext';
import { Button, Card } from './ui';

export function HowItWorks() {
  const { styles } = useTheme();
  const [expanded, setExpanded] = useState(false);
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
