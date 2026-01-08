#!/usr/bin/bash
# ALPM hook script for ugrd
# Called when kernel packages are installed or upgraded

set -e

# If KERNEL_INSTALL_INITRD_GENERATOR is set, disable this hook
if [ -n "$KERNEL_INSTALL_INITRD_GENERATOR" ]; then
    exit 0
fi

while read -r line; do
    if [[ "$line" == 'usr/lib/modules/'+([^/])'/pkgbase' ]]; then
        read -r pkgbase < "/${line}"
        kver="${line#'usr/lib/modules/'}"
        kver="${kver%'/pkgbase'}"

        echo "==> Building initramfs for ${pkgbase} (${kver})"
        install -Dm0644 "/${line%'/pkgbase'}/vmlinuz" "/boot/vmlinuz-${pkgbase}"
        ugrd --kver "$kver" "/boot/initramfs-${pkgbase}.img"
    fi
done
