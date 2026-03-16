#!/bin/bash
# Setlist Navigator — WiFi Hotspot Setup
# Makes the Pi broadcast its own WiFi network at gigs.
# Run ONCE as normal user:  bash setup-hotspot.sh
# WARNING: This will replace existing wlan0 config.

SSID="SetlistNavigator"
PASS="rockandroll"
IP="192.168.50.1"

echo ""
echo "══════════════════════════════════════"
echo "  Setting up WiFi Hotspot"
echo "  SSID: $SSID  |  Pass: $PASS"
echo "══════════════════════════════════════"
echo ""

# Stop conflicting services
sudo systemctl stop hostapd dnsmasq 2>/dev/null || true
sudo systemctl unmask hostapd

# hostapd config
sudo tee /etc/hostapd/hostapd.conf > /dev/null << EOF
interface=wlan0
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

sudo sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

# dnsmasq config (DHCP + DNS redirect to Pi)
sudo cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bak 2>/dev/null || true
sudo tee /etc/dnsmasq.conf > /dev/null << EOF
interface=wlan0
dhcp-range=192.168.50.10,192.168.50.50,255.255.255.0,24h
address=/#/$IP
EOF

# Static IP for wlan0
sudo tee /etc/network/interfaces.d/wlan0-hotspot > /dev/null << EOF
allow-hotplug wlan0
iface wlan0 inet static
    address $IP
    netmask 255.255.255.0
EOF

# Apply static IP now
sudo ip addr add $IP/24 dev wlan0 2>/dev/null || true

# Enable & start
sudo systemctl enable hostapd dnsmasq
sudo systemctl start hostapd dnsmasq

echo ""
echo "✓ Hotspot is live!"
echo ""
echo "  WiFi name : $SSID"
echo "  Password  : $PASS"
echo "  Leader URL: http://$IP:8000/leader"
echo "  Stage URL : http://$IP:8000/"
echo ""
echo "  Connect tablets to '$SSID' and open http://$IP:8000"
echo ""
