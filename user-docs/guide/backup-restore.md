# Backup & Restore

## What Gets Backed Up

Your Voxel backup includes all personal settings:

- Gateway connection (URL and token)
- Audio preferences (volume, TTS provider)
- Display settings (brightness, transitions)
- Agent selection and configuration
- WiFi setup completion status

Backups are saved as a single JSON file that can be transferred between devices.

## Export a Backup

### From the Web Interface

1. Open your Voxel's config page (scan the QR code on the LCD or go to the IP shown on screen)
2. Enter your PIN
3. Navigate to the backup section
4. Click **Export Backup** -- a `voxel-backup.json` file will download

### From the Command Line

```bash
voxel backup export                    # Saves to voxel-backup.json
voxel backup export -o my-backup.json  # Custom filename
```

## Restore from Backup

### From the Web Interface

1. Open the config page and authenticate
2. Navigate to the backup section
3. Upload your `voxel-backup.json` file
4. Restart the device for changes to take effect

### From the Command Line

```bash
voxel backup import voxel-backup.json
voxel restart  # Apply changes
```

## Factory Reset

Resets all settings to defaults. You'll need to reconfigure WiFi, gateway token, and preferences.

### From the Web Interface

1. Open the config page
2. Navigate to the backup section
3. Click **Factory Reset** and confirm

### From the Command Line

```bash
voxel backup factory-reset      # Will ask for confirmation
voxel backup factory-reset -y   # Skip confirmation
```

::: tip
Export a backup before factory resetting so you can restore later.
:::

## Security Note

Backup files contain your API tokens and passwords. Keep them secure and don't share them publicly.
