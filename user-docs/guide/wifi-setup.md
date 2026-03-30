# WiFi Setup

Voxel includes a built-in WiFi onboarding system for headless setup. If the device has no known WiFi network on boot, it automatically creates a hotspot and serves a configuration portal.

## How AP Mode Works

On startup, the display service checks for a WiFi connection. If none is found:

1. The device creates a WiFi hotspot called **Voxel-Setup**
2. The LCD shows the AP mode screen with connection instructions and a QR code
3. A web configuration portal starts on port 8081

The device uses `nmcli` (NetworkManager) for all WiFi operations — no extra packages needed.

::: info
The Pi Zero 2W has a single WiFi radio (CYW43436). AP mode and client mode are mutually exclusive — the device cannot be a hotspot and connect to your network at the same time.
:::

## Connecting to the Hotspot

1. On your phone or laptop, scan for WiFi networks
2. Connect to **Voxel-Setup**
   - Password: `voxel1234`
3. Open a browser and navigate to `http://10.42.0.1:8081`
   - Or scan the QR code displayed on the device's LCD

## Configuring WiFi

1. **Enter the PIN** shown on the device's LCD screen (6-digit code, regenerated on each boot)
2. The config portal shows available WiFi networks
3. **Select your network** from the list
4. **Enter the WiFi password**
5. Click **Connect**

The device will:

1. Disconnect the hotspot
2. Connect to your selected network
3. Exit AP mode
4. Restart the display service

The animated face should appear on the LCD within a few seconds of a successful connection.

## Verifying the Connection

After the device connects to WiFi, you can SSH in using its hostname or IP:

```bash
ssh pi@voxel.local
```

Check the IP address from the device itself:

```bash
hostname -I
```

## Re-entering AP Mode

If you need to change WiFi networks or the device cannot connect:

**Method 1 — Remove saved networks:**

```bash
ssh pi@voxel.local
sudo nmcli connection delete <network-name>
sudo reboot
```

The device will enter AP mode on the next boot since no known network is available.

**Method 2 — Manually start AP mode:**

```bash
ssh pi@voxel.local
voxel stop
# The display service will detect no WiFi and start AP mode on next start
voxel start
```

## Troubleshooting

### Cannot see the Voxel-Setup hotspot

- Ensure the device is powered on and has booted fully (wait 60 seconds)
- The hotspot only appears when no known WiFi network is in range
- Check that the Whisplay HAT is properly seated on the GPIO header

### Connected to hotspot but cannot reach the portal

- Verify you are connected to Voxel-Setup, not your home network
- Try navigating directly to `http://10.42.0.1:8081`
- Some phones auto-switch back to mobile data — disable mobile data temporarily

### WiFi network not appearing in the list

- The scan may take a few seconds; refresh the page
- The device only sees 2.4GHz networks (Pi Zero 2W limitation)
- Ensure your router broadcasts the SSID (hidden networks are not listed)

### Connection fails after entering password

- Double-check the WiFi password
- Ensure the network uses WPA2 (WPA3-only networks may not work)
- Move the device closer to the router for initial setup
- Check `voxel logs` for connection error details

### Device connected but cannot reach the internet

- Verify your router has internet access from another device
- Check DNS resolution: `ping google.com` from an SSH session
- Some networks require a captive portal login — these are not supported in AP onboarding
