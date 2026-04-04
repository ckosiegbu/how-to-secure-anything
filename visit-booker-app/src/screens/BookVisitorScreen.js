import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Switch,
  Platform,
  Alert,
} from 'react-native';
import * as Contacts from 'expo-contacts';
import DateTimePicker from '@react-native-community/datetimepicker';
import Slider from '@react-native-community/slider';
import Colors from '../utils/colors';
import { generateToken } from '../utils/codeGenerator';

const COUNTRY_CODES = ['+234', '+1', '+44', '+91', '+27'];
const ENTRY_OPTIONS = [1, 2, 3, 4, 5];

export default function BookVisitorScreen({ navigation }) {
  const [visitorName, setVisitorName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [countryCode, setCountryCode] = useState('+234');
  const [showCountryPicker, setShowCountryPicker] = useState(false);
  const [numberOfEntries, setNumberOfEntries] = useState(1);
  const [showEntriesPicker, setShowEntriesPicker] = useState(false);
  const [numberOfVisitors, setNumberOfVisitors] = useState('1');
  const [repeatingVisit, setRepeatingVisit] = useState(false);
  const [dateOfVisit, setDateOfVisit] = useState(new Date());
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [codeValidity, setCodeValidity] = useState(3);
  const [additionalComments, setAdditionalComments] = useState('');

  const pickContact = useCallback(async () => {
    try {
      const { status } = await Contacts.requestPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Contact access is required to select a visitor.');
        return;
      }
      const { data } = await Contacts.getContactsAsync({
        fields: [Contacts.Fields.PhoneNumbers, Contacts.Fields.Name],
      });
      if (data.length > 0) {
        // Show a simple selection - pick first contact with phone number
        const contactsWithPhone = data.filter(
          (c) => c.phoneNumbers && c.phoneNumbers.length > 0
        );
        if (contactsWithPhone.length === 0) {
          Alert.alert('No Contacts', 'No contacts with phone numbers found.');
          return;
        }
        // For simplicity, show an alert with first 10 contacts
        const options = contactsWithPhone.slice(0, 20);
        // Use navigation to a contact picker or simple alert
        const buttons = options.slice(0, 5).map((contact) => ({
          text: `${contact.name} (${contact.phoneNumbers[0].number})`,
          onPress: () => {
            setVisitorName(contact.name || '');
            const rawNum = contact.phoneNumbers[0].number || '';
            // Strip country code if present
            const cleaned = rawNum.replace(/[\s\-\(\)]/g, '');
            setPhoneNumber(cleaned.startsWith('+') ? cleaned.slice(4) : cleaned);
          },
        }));
        buttons.push({ text: 'Cancel', style: 'cancel' });
        Alert.alert('Select Contact', 'Choose a contact:', buttons);
      }
    } catch (err) {
      Alert.alert('Error', 'Could not access contacts.');
    }
  }, []);

  const handleDateChange = (event, selectedDate) => {
    setShowDatePicker(false);
    if (selectedDate) {
      const updated = new Date(dateOfVisit);
      updated.setFullYear(selectedDate.getFullYear());
      updated.setMonth(selectedDate.getMonth());
      updated.setDate(selectedDate.getDate());
      setDateOfVisit(updated);
    }
  };

  const handleTimeChange = (event, selectedTime) => {
    setShowTimePicker(false);
    if (selectedTime) {
      const updated = new Date(dateOfVisit);
      updated.setHours(selectedTime.getHours());
      updated.setMinutes(selectedTime.getMinutes());
      updated.setSeconds(selectedTime.getSeconds());
      setDateOfVisit(updated);
    }
  };

  const formatDate = (date) => {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${String(date.getDate()).padStart(2, '0')} ${months[date.getMonth()]} ${date.getFullYear()}`;
  };

  const formatTime = (date) => {
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`;
  };

  const handleBookVisit = () => {
    if (!visitorName.trim()) {
      Alert.alert('Required', "Please enter the visitor's name.");
      return;
    }

    const token = generateToken();
    const validFrom = new Date(dateOfVisit);
    const validUntil = new Date(dateOfVisit);
    validUntil.setHours(validUntil.getHours() + codeValidity);

    navigation.navigate('BookingSuccess', {
      token,
      visitorName: visitorName.trim(),
      phoneNumber: `${countryCode}${phoneNumber}`,
      validFrom: validFrom.toISOString(),
      validUntil: validUntil.toISOString(),
      propertyUnit: 'D19 - EC',
      numberOfVisitors,
      codeValidity,
    });
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Events & Visitors</Text>
          <Text style={styles.headerSubtitle}>Earls Court - D19 - EC</Text>
        </View>
        <TouchableOpacity style={styles.historyBtn}>
          <Text style={styles.historyText}>History</Text>
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={styles.tabContainer}>
        <TouchableOpacity style={[styles.tab, styles.activeTab]}>
          <Text style={styles.activeTabText}>Book Visitors</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.tab}>
          <Text style={styles.tabText}>Create an Event</Text>
          <View style={styles.newBadge}>
            <Text style={styles.newBadgeText}>New</Text>
          </View>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.form} showsVerticalScrollIndicator={false}>
        {/* Visitor Name */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Visitor's Name *</Text>
          <TextInput
            style={styles.input}
            value={visitorName}
            onChangeText={setVisitorName}
            placeholder="Enter visitor name"
            placeholderTextColor={Colors.textLight}
          />
        </View>

        {/* Phone Number */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Phone Number</Text>
          <View style={styles.phoneRow}>
            <TouchableOpacity
              style={styles.countryCodeBtn}
              onPress={() => setShowCountryPicker(!showCountryPicker)}
            >
              <Text style={styles.countryCodeText}>{countryCode}</Text>
              <Text style={styles.dropdownArrow}>▼</Text>
            </TouchableOpacity>
            <TextInput
              style={[styles.input, styles.phoneInput]}
              value={phoneNumber}
              onChangeText={setPhoneNumber}
              placeholder="Phone number"
              placeholderTextColor={Colors.textLight}
              keyboardType="phone-pad"
            />
            <TouchableOpacity style={styles.contactBtn} onPress={pickContact}>
              <Text style={styles.contactIcon}>👤</Text>
            </TouchableOpacity>
          </View>
        </View>

        {showCountryPicker && (
          <View style={styles.pickerDropdown}>
            {COUNTRY_CODES.map((code) => (
              <TouchableOpacity
                key={code}
                style={styles.pickerItem}
                onPress={() => {
                  setCountryCode(code);
                  setShowCountryPicker(false);
                }}
              >
                <Text style={styles.pickerItemText}>{code}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Number of Entries & Visitors */}
        <View style={styles.row}>
          <View style={[styles.inputGroup, { flex: 1, marginRight: 10 }]}>
            <Text style={styles.label}>Number of Entries</Text>
            <TouchableOpacity
              style={styles.selectInput}
              onPress={() => setShowEntriesPicker(!showEntriesPicker)}
            >
              <Text style={styles.selectText}>{numberOfEntries}</Text>
              <Text style={styles.dropdownArrow}>▼</Text>
            </TouchableOpacity>
            {showEntriesPicker && (
              <View style={styles.pickerDropdown}>
                {ENTRY_OPTIONS.map((n) => (
                  <TouchableOpacity
                    key={n}
                    style={styles.pickerItem}
                    onPress={() => {
                      setNumberOfEntries(n);
                      setShowEntriesPicker(false);
                    }}
                  >
                    <Text style={styles.pickerItemText}>{n}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            <Text style={styles.helperText}>
              No of times code can be used within validity period.
            </Text>
          </View>
          <View style={[styles.inputGroup, { flex: 1 }]}>
            <Text style={styles.label}>Number Of Visitors *</Text>
            <TextInput
              style={styles.input}
              value={numberOfVisitors}
              onChangeText={setNumberOfVisitors}
              keyboardType="number-pad"
            />
          </View>
        </View>

        {/* Repeating Visit */}
        <View style={styles.repeatRow}>
          <Text style={styles.repeatLabel}>Repeating Visit?</Text>
          <Switch
            value={repeatingVisit}
            onValueChange={setRepeatingVisit}
            trackColor={{ false: '#ccc', true: Colors.accent }}
            thumbColor={Colors.white}
          />
        </View>

        {/* Date and Time */}
        <View style={styles.row}>
          <View style={[styles.inputGroup, { flex: 1, marginRight: 10 }]}>
            <Text style={styles.label}>Date of Visit</Text>
            <TouchableOpacity
              style={styles.selectInput}
              onPress={() => setShowDatePicker(true)}
            >
              <Text style={styles.selectText}>{formatDate(dateOfVisit)}</Text>
              <Text style={styles.calendarIcon}>📅</Text>
            </TouchableOpacity>
          </View>
          <View style={[styles.inputGroup, { flex: 1 }]}>
            <Text style={styles.label}>Time of Visit</Text>
            <TouchableOpacity
              style={styles.selectInput}
              onPress={() => setShowTimePicker(true)}
            >
              <Text style={styles.selectText}>{formatTime(dateOfVisit)}</Text>
              <Text style={styles.calendarIcon}>🕐</Text>
            </TouchableOpacity>
          </View>
        </View>

        {showDatePicker && (
          <DateTimePicker
            value={dateOfVisit}
            mode="date"
            display={Platform.OS === 'ios' ? 'spinner' : 'default'}
            onChange={handleDateChange}
          />
        )}
        {showTimePicker && (
          <DateTimePicker
            value={dateOfVisit}
            mode="time"
            display={Platform.OS === 'ios' ? 'spinner' : 'default'}
            onChange={handleTimeChange}
          />
        )}

        {/* Code Validity Slider */}
        <View style={styles.sliderGroup}>
          <View style={styles.sliderHeader}>
            <Text style={styles.sliderLabel}>Code Validity (Hours)</Text>
            <Text style={styles.sliderValue}>{codeValidity} hr</Text>
          </View>
          <Slider
            style={styles.slider}
            minimumValue={1}
            maximumValue={6}
            step={1}
            value={codeValidity}
            onValueChange={setCodeValidity}
            minimumTrackTintColor={Colors.info}
            maximumTrackTintColor={Colors.border}
            thumbTintColor={Colors.info}
          />
          <View style={styles.sliderRange}>
            <Text style={styles.rangeText}>1 hr</Text>
            <Text style={styles.rangeText}>6 hr</Text>
          </View>
        </View>

        {/* Additional Comments */}
        <View style={styles.inputGroup}>
          <TextInput
            style={[styles.input, styles.textArea]}
            value={additionalComments}
            onChangeText={setAdditionalComments}
            placeholder="Additional Comments"
            placeholderTextColor={Colors.textLight}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />
        </View>

        {/* Book Visit Button */}
        <TouchableOpacity style={styles.bookBtn} onPress={handleBookVisit}>
          <Text style={styles.bookBtnText}>Book Visit</Text>
        </TouchableOpacity>

        <View style={{ height: 40 }} />
      </ScrollView>
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
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: { color: Colors.white, fontSize: 20, fontWeight: '700' },
  headerSubtitle: { color: '#aab7c4', fontSize: 13, marginTop: 2 },
  historyBtn: {
    backgroundColor: Colors.white,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  historyText: { color: Colors.primary, fontWeight: '600', fontSize: 14 },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: Colors.white,
    paddingHorizontal: 16,
    paddingTop: 10,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
  },
  activeTab: {
    backgroundColor: Colors.primary,
    borderRadius: 8,
  },
  activeTabText: { color: Colors.white, fontWeight: '600', fontSize: 15 },
  tabText: { color: Colors.text, fontWeight: '500', fontSize: 15 },
  newBadge: {
    backgroundColor: '#FF6B35',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: 6,
  },
  newBadgeText: { color: Colors.white, fontSize: 10, fontWeight: '700' },
  form: { flex: 1, paddingHorizontal: 16, paddingTop: 16 },
  inputGroup: { marginBottom: 16 },
  label: { fontSize: 13, color: Colors.textLight, marginBottom: 6, fontWeight: '500' },
  input: {
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
    color: Colors.text,
  },
  phoneRow: { flexDirection: 'row', alignItems: 'center' },
  countryCodeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 14,
    marginRight: 8,
  },
  countryCodeText: { fontSize: 16, color: Colors.text, marginRight: 6 },
  dropdownArrow: { fontSize: 10, color: Colors.textLight },
  phoneInput: { flex: 1 },
  contactBtn: {
    backgroundColor: Colors.info,
    borderRadius: 10,
    padding: 14,
    marginLeft: 8,
  },
  contactIcon: { fontSize: 18 },
  pickerDropdown: {
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 8,
    marginTop: 4,
    overflow: 'hidden',
  },
  pickerItem: { padding: 12, borderBottomWidth: 1, borderBottomColor: Colors.border },
  pickerItemText: { fontSize: 15, color: Colors.text },
  row: { flexDirection: 'row' },
  selectInput: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  selectText: { fontSize: 16, color: Colors.text },
  calendarIcon: { fontSize: 18 },
  helperText: { fontSize: 11, color: Colors.error, marginTop: 4 },
  repeatRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
    paddingVertical: 8,
  },
  repeatLabel: { fontSize: 18, fontWeight: '600', color: Colors.text },
  sliderGroup: { marginBottom: 20 },
  sliderHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  sliderLabel: { fontSize: 16, fontWeight: '700', color: Colors.text },
  sliderValue: { fontSize: 18, fontWeight: '700', color: Colors.info },
  slider: { width: '100%', height: 40 },
  sliderRange: { flexDirection: 'row', justifyContent: 'space-between' },
  rangeText: { fontSize: 12, color: Colors.textLight },
  textArea: { height: 120, paddingTop: 14 },
  bookBtn: {
    backgroundColor: Colors.accent,
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 10,
  },
  bookBtnText: { fontSize: 18, fontWeight: '700', color: Colors.text },
});
