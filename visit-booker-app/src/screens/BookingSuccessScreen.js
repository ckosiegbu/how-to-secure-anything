import React, { useRef, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Linking,
  Platform,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import QRCode from 'react-native-qrcode-svg';
import Colors from '../utils/colors';

export default function BookingSuccessScreen({ route, navigation }) {
  const { token, visitorName, phoneNumber, validFrom, validUntil, propertyUnit } = route.params;
  const qrRef = useRef(null);

  const fromDate = new Date(validFrom);
  const untilDate = new Date(validUntil);

  const formatDateTime = (date) => {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const h = hours % 12 || 12;
    return `${h}:${minutes} ${ampm} ${months[date.getMonth()]} ${String(date.getDate()).padStart(2, '0')}, ${date.getFullYear()}`;
  };

  const copyToken = useCallback(async () => {
    try {
      await Clipboard.setStringAsync(token);
      Alert.alert('Copied', 'Token copied to clipboard.');
    } catch {
      Alert.alert('Error', 'Could not copy token.');
    }
  }, [token]);

  const getQRBase64 = () => {
    return new Promise((resolve) => {
      if (qrRef.current) {
        qrRef.current.toDataURL((data) => {
          resolve(data);
        });
      } else {
        resolve(null);
      }
    });
  };

  const shareWhatsApp = useCallback(async () => {
    try {
      // Save QR code as image
      const qrData = await getQRBase64();
      let qrFilePath = null;

      if (qrData) {
        qrFilePath = `${FileSystem.cacheDirectory}visit_token_${token}.png`;
        await FileSystem.writeAsStringAsync(qrFilePath, qrData, {
          encoding: FileSystem.EncodingType.Base64,
        });
      }

      const message =
        `🎫 *Visit Booker - Visitor Token*\n\n` +
        `👤 Visitor: ${visitorName}\n` +
        `🔑 Token: *${token}*\n` +
        `📍 Property: ${propertyUnit}\n` +
        `⏰ Valid: ${formatDateTime(fromDate)} - ${formatDateTime(untilDate)}\n\n` +
        `Please present this token at the gate.`;

      // Clean phone number for WhatsApp
      const cleanPhone = phoneNumber.replace(/[\s\-\(\)\+]/g, '');

      // Try sharing via WhatsApp with image
      if (qrFilePath && await Sharing.isAvailableAsync()) {
        // First share the QR image
        await Sharing.shareAsync(qrFilePath, {
          mimeType: 'image/png',
          dialogTitle: 'Share Visitor Token QR Code',
        });
      }

      // Open WhatsApp with the message
      const whatsappUrl = `whatsapp://send?phone=${cleanPhone}&text=${encodeURIComponent(message)}`;
      const canOpen = await Linking.canOpenURL(whatsappUrl);

      if (canOpen) {
        await Linking.openURL(whatsappUrl);
      } else {
        // Fallback to web WhatsApp
        const webUrl = `https://wa.me/${cleanPhone}?text=${encodeURIComponent(message)}`;
        await Linking.openURL(webUrl);
      }
    } catch (err) {
      Alert.alert('Error', 'Could not share via WhatsApp. Make sure WhatsApp is installed.');
    }
  }, [token, visitorName, phoneNumber, propertyUnit, fromDate, untilDate]);

  const shareSMS = useCallback(async () => {
    const message =
      `Visit Booker Token\nVisitor: ${visitorName}\nToken: ${token}\nProperty: ${propertyUnit}\nValid: ${formatDateTime(fromDate)} - ${formatDateTime(untilDate)}`;

    const cleanPhone = phoneNumber.replace(/[\s\-\(\)]/g, '');
    const smsUrl = Platform.OS === 'ios'
      ? `sms:${cleanPhone}&body=${encodeURIComponent(message)}`
      : `sms:${cleanPhone}?body=${encodeURIComponent(message)}`;

    try {
      await Linking.openURL(smsUrl);
    } catch {
      Alert.alert('Error', 'Could not open SMS app.');
    }
  }, [token, visitorName, phoneNumber, propertyUnit, fromDate, untilDate]);

  const shareGeneral = useCallback(async () => {
    try {
      const qrData = await getQRBase64();
      if (qrData) {
        const filePath = `${FileSystem.cacheDirectory}visit_token_${token}.png`;
        await FileSystem.writeAsStringAsync(filePath, qrData, {
          encoding: FileSystem.EncodingType.Base64,
        });
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(filePath, {
            mimeType: 'image/png',
            dialogTitle: 'Share Visitor Token',
          });
        }
      }
    } catch {
      Alert.alert('Error', 'Could not share.');
    }
  }, [token]);

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backArrow}>←</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        <Text style={styles.title}>Booking Successful</Text>

        {/* Details Card */}
        <View style={styles.detailsCard}>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Valid From</Text>
            <Text style={styles.detailValue}>{formatDateTime(fromDate)}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Until</Text>
            <Text style={styles.detailValue}>{formatDateTime(untilDate)}</Text>
          </View>
          <View style={[styles.detailRow, { borderBottomWidth: 0 }]}>
            <Text style={styles.detailLabel}>Property Unit</Text>
            <Text style={styles.detailValue}>{propertyUnit}</Text>
          </View>
        </View>

        {/* Token Display */}
        <View style={styles.tokenCard}>
          <Text style={styles.tokenLabel}>Visitor Token:</Text>
          <View style={styles.tokenRow}>
            <Text style={styles.tokenText}>{token}</Text>
            <TouchableOpacity style={styles.copyBtn} onPress={copyToken}>
              <Text style={styles.copyIcon}>📋</Text>
              <Text style={styles.copyText}>Copy Token</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* QR Code */}
        <View style={styles.qrContainer}>
          <QRCode
            value={token}
            size={150}
            backgroundColor={Colors.white}
            color={Colors.text}
            getRef={(ref) => (qrRef.current = ref)}
          />
        </View>

        {/* Share Options */}
        <Text style={styles.shareTitle}>Share Token</Text>
        <View style={styles.shareRow}>
          <TouchableOpacity style={styles.shareBtn} onPress={shareSMS}>
            <View style={styles.shareIconContainer}>
              <Text style={styles.shareIcon}>💬</Text>
            </View>
            <Text style={styles.shareLabel}>SMS</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.shareBtn} onPress={shareWhatsApp}>
            <View style={[styles.shareIconContainer, { backgroundColor: Colors.whatsapp }]}>
              <Text style={styles.shareIcon}>📱</Text>
            </View>
            <Text style={[styles.shareLabel, { fontWeight: '700' }]}>WhatsApp</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.shareBtn} onPress={shareGeneral}>
            <View style={styles.shareIconContainer}>
              <Text style={styles.shareIcon}>🔗</Text>
            </View>
            <Text style={styles.shareLabel}>Share</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  header: {
    backgroundColor: Colors.primary,
    paddingTop: 50,
    paddingBottom: 15,
    paddingHorizontal: 20,
    flexDirection: 'row',
    alignItems: 'center',
  },
  backBtn: { padding: 4 },
  backArrow: { color: Colors.white, fontSize: 24, fontWeight: '700' },
  content: { flex: 1, paddingHorizontal: 20, paddingTop: 30, alignItems: 'center' },
  title: { fontSize: 26, fontWeight: '700', color: Colors.text, marginBottom: 24 },
  detailsCard: {
    backgroundColor: Colors.white,
    borderRadius: 12,
    padding: 16,
    width: '100%',
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: 20,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  detailLabel: { fontSize: 14, color: Colors.textLight },
  detailValue: { fontSize: 14, fontWeight: '600', color: Colors.text },
  tokenCard: {
    backgroundColor: Colors.tokenBg,
    borderWidth: 2,
    borderColor: Colors.tokenBorder,
    borderRadius: 12,
    padding: 20,
    width: '100%',
    alignItems: 'center',
    marginBottom: 20,
  },
  tokenLabel: { fontSize: 16, color: Colors.textLight, marginBottom: 10 },
  tokenRow: { flexDirection: 'row', alignItems: 'center' },
  tokenText: { fontSize: 36, fontWeight: '800', color: Colors.text, letterSpacing: 4, marginRight: 16 },
  copyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  copyIcon: { fontSize: 16, marginRight: 4 },
  copyText: { fontSize: 13, color: Colors.textLight },
  qrContainer: {
    backgroundColor: Colors.white,
    padding: 20,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Colors.border,
    marginBottom: 24,
  },
  shareTitle: { fontSize: 18, fontWeight: '700', color: Colors.text, marginBottom: 16 },
  shareRow: { flexDirection: 'row', justifyContent: 'center', gap: 40 },
  shareBtn: { alignItems: 'center' },
  shareIconContainer: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#ECEFF1',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  shareIcon: { fontSize: 28 },
  shareLabel: { fontSize: 14, color: Colors.text },
});
