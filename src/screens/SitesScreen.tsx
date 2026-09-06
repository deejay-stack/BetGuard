import React from 'react';
import { Alert, Text, View } from 'react-native';
import { useBetGuard } from '../state/BetGuardContext';
import { Badge, Button, Card, Empty, Loading, Page } from '../components/ui';
import { RuleEditor } from '../components/RuleEditor';
import { styles } from '../theme';
export function SitesScreen() {
  const { snapshot, busy, available, save, remove } = useBetGuard();
  return (
    <Page
      title="Your site rules."
      subtitle="A saved choice stays in place until you change it."
    >
      <RuleEditor />
      <Text style={styles.heading}>
        Saved rules {snapshot ? `(${snapshot.rules.length})` : ''}
      </Text>
      {!snapshot && available && <Loading />}
      {snapshot?.rules.length === 0 && (
        <Card>
          <Empty
            title="No rules yet"
            body="Start with a harmless test domain such as example.com. A manual block does not label it as gambling."
          />
        </Card>
      )}
      {snapshot?.rules.map(rule => (
        <Card key={rule.domain}>
          <View style={styles.spread}>
            <Text selectable style={[styles.heading, styles.flex]}>
              {rule.domain}
            </Text>
            <Badge
              text={rule.action === 'block' ? 'BLOCK RULE' : 'ALLOW RULE'}
              tone={rule.action === 'block' ? 'red' : 'green'}
            />
          </View>
          <Text style={styles.small}>
            {rule.includeSubdomains
              ? 'Hostname and subdomains'
              : 'Exact hostname only'}{' '}
            · Saved locally
          </Text>
          <View style={styles.wrap}>
            <Button
              title={rule.action === 'block' ? 'Allow site' : 'Block site'}
              secondary
              disabled={busy}
              onPress={() => {
                void save(
                  rule.domain,
                  rule.action === 'block' ? 'allow' : 'block',
                  rule.includeSubdomains,
                );
              }}
            />
            <Button
              title="Return to automatic"
              secondary
              disabled={busy}
              onPress={() =>
                Alert.alert(
                  'Remove this override?',
                  'Another matching rule may still apply. Otherwise, this prototype allows the site with classification unknown.',
                  [
                    { text: 'Cancel', style: 'cancel' },
                    {
                      text: 'Remove override',
                      onPress: () => {
                        void remove(rule.domain);
                      },
                    },
                  ],
                )
              }
            />
          </View>
        </Card>
      ))}
    </Page>
  );
}
