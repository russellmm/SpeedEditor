#!/usr/bin/env bash
# Run once with sudo or pkexec. Grants only active local users access.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  printf 'Run: sudo bash "%s"\n' "$(readlink -f -- "$0")" >&2
  exit 1
fi
command -v setfacl >/dev/null
command -v udevadm >/dev/null
install -d -m 0755 /etc/udev/rules.d
# Filename precedes 73-seat-late.rules so systemd can apply the uaccess tag.
cat > /etc/udev/rules.d/70-speededitor.rules <<'RULES'
# SpeedEditor USB HID only; no access to other keyboards or mice.
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1edb", ATTRS{idProduct}=="da0e", TAG+="uaccess"
# Allows the active local user to create virtual keyboard/scroll events.
SUBSYSTEM=="misc", KERNEL=="uinput", TAG+="uaccess"
RULES
chmod 0644 /etc/udev/rules.d/70-speededitor.rules
modprobe uinput
udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw
udevadm trigger --subsystem-match=misc --sysname-match=uinput
udevadm settle
# Apply access immediately for the active local session, also when started via pkexec.
task_uid="${SUDO_UID:-${PKEXEC_UID:-}}"
if [ -n "$task_uid" ] && [ "$task_uid" != 0 ] && [[ "$task_uid" =~ ^[0-9]+$ ]]; then
  for candidate in /sys/class/hidraw/hidraw*; do
    if [ -f "$candidate/device/uevent" ] &&
       grep -q '^HID_ID=0003:00001EDB:0000DA0E$' "$candidate/device/uevent"; then
      setfacl -m "u:${task_uid}:rw" "/dev/${candidate##*/}"
    fi
  done
  setfacl -m "u:${task_uid}:rw" /dev/uinput
fi
printf 'SpeedEditor USB and virtual keyboard access configured.\n'
