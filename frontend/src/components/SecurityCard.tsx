import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { ChevronRight, type LucideIcon } from 'lucide-react-native';
import { useTheme } from '../state/ThemeContext';
import { Badge } from './ui';
export function SecurityCard({
  title,
  value,
  detail,
  icon: Icon,
  tone = 'primary',
  onPress,
}: {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  tone?: 'primary' | 'success' | 'warning' | 'error' | 'inactive';
  onPress: () => void;
}) {
  const { colors, styles } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}, ${value}. ${detail}`}
      onPress={onPress}
      style={({ pressed }) => [
        local.card,
        {
          backgroundColor: pressed ? colors.surfaceElevated : colors.surface,
          borderColor: colors.border,
        },
      ]}
    >
      <View style={styles.spread}>
        <Icon color={colors[tone]} size={24} />
        <ChevronRight color={colors.textMuted} size={16} />
      </View>
      <Text style={styles.body}>{title}</Text>
      <Badge text={value} tone={tone} />
      <Text style={styles.small}>{detail}</Text>
    </Pressable>
  );
}
const local = StyleSheet.create({
  card: {
    flexGrow: 1,
    flexBasis: '45%',
    minWidth: 140,
    padding: 20,
    borderRadius: 24,
    borderWidth: 1,
    gap: 12,
  },
});
