## How does UGRD compare to other generators?

### Run time

People say python is slow, but UGRD is very fast, even on slow hardware.

#### Raspberry pi 3

Using a rpi3 on powersave:

```
time dracut --no-compress --force

real    0m56.537s
user    0m41.309s
sys     0m15.989s
```

```
time ugrd --no-compress

real    0m6.599s
user    0m3.744s
sys     0m2.147s
```

##### Compression

ugrd compression is limited by single thread python performance, but still builds faster than dracut which calls zstd:

```
time dracut --force

real    1m6.812s
user    1m0.391s
sys     0m16.300s
```

```
time ugrd

real    0m37.686s
user    0m35.386s
sys     0m2.510s
```

#### 7950x

```
time dracut --no-compress --force 

real	0m7.142s
user	0m3.233s
sys     0m4.811s
```

```
time ugrd --no-compress

real	0m0.864s
user	0m0.424s
sys     0m0.583s
```

##### Compression

```
time dracut --force

real	0m9.653s
user	0m29.121s
sys     0m5.253s
```

```
real	0m13.011s
user	0m12.349s
sys     0m0.643s
```

> Here, dracut is able to run faster by making use of threading with the zstd utility, python xz currently does not thread
> https://github.com/python/cpython/pull/114954


### Image size

ugrd makes very small images, even with no compression, it creates smaller images than dracut with zstd compression!

#### Raspberry pi 3

| Generator | Compression   | Size  | Mode     |
|-----------|---------------|-------|----------|
| dracut    | none          | 30M   | hostonly |
| dracut    | none          | 24M   | standard |
| dracut    | zstd          | 13M   | standard |
| ugrd      | none          | 9.41M | hostonly |
| dracut    | zstd          | 8.5M  | hostonly |
| ugrd      | xz (default)  | 2.64M | hostonly |


#### 7950x

| Generator | Compression   | Size   | Mode     |
|-----------|---------------|--------|----------|
| dracut    | none          | 392M   | standard |
| dracut    | none          | 192M   | hostonly |
| dracut    | zstd          | 91M    | standard |
| ugrd      | none          | 65.36M | hostonly |
| dracut    | zstd          | 49M    | hostonly |
| ugrd      | xz (default)  | 18.89M | hostonly |

> For this image, luks, gpg, and yubikey modules are required, greatly increasing the image size

### Boot time

ugrd boots faster than dracut, even without udev:

Dracut boot:
```
[    3.106933]     recovery
[    3.106939]   with environment:
[    3.106945]     HOME=/
[    3.106951]     TERM=linux
[    3.142999] mmc0: host does not support reading read-only switch, assuming write-enable
[    3.149037] mmc0: Host Software Queue enabled
[    3.150788] mmc0: new high speed SDHC card at address aaaa
[    3.154389] mmcblk0: mmc0:aaaa SL16G 14.8 GiB
[    3.164336]  mmcblk0: p1 p2
[    3.166987] mmcblk0: mmc0:aaaa SL16G 14.8 GiB (quirks 0x00004000)
[    3.174279] mmc1: new high speed SDIO card at address 0001
[    3.177061] usb 1-1: new high-speed USB device number 2 using dwc_otg
[    3.178984] Indeed it is in host mode hprt0 = 00001101
[    3.385637] usb 1-1: New USB device found, idVendor=0424, idProduct=9514, bcdDevice= 2.00
[    3.389174] usb 1-1: New USB device strings: Mfr=0, Product=0, SerialNumber=0
[    3.392006] hub 1-1:1.0: USB hub found
[    3.394109] hub 1-1:1.0: 5 ports detected
[    3.554215] dracut: Gentoo-2.17
[    3.690010] usb 1-1.1: new high-speed USB device number 3 using dwc_otg
[    3.792071] usb 1-1.1: New USB device found, idVendor=0424, idProduct=ec00, bcdDevice= 2.00
[    3.795715] usb 1-1.1: New USB device strings: Mfr=0, Product=0, SerialNumber=0
[    3.800751] smsc95xx v2.0.0
[    3.906640] SMSC LAN8700 usb-001:003:01: attached PHY driver (mii_bus:phy_addr=usb-001:003:01, irq=184)
[    3.911722] smsc95xx 1-1.1:1.0 eth0: register 'smsc95xx' at usb-3f980000.usb-1.1, smsc95xx USB 2.0 Ethernet, b8:27:eb:0c:d0:4b
[    5.151361] EXT4-fs (mmcblk0p2): mounted filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b ro with ordered data mode. Quota mode: none.
[    5.286768] EXT4-fs (mmcblk0p2): unmounting filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b.
[    5.337578] dracut: Checking ext4: /dev/mmcblk0p2
[    5.340808] dracut: issuing e2fsck -a /dev/mmcblk0p2
[    5.373619] dracut: rootfs: clean, 247841/908960 files, 815408/3757440 blocks
[    5.389944] dracut: Mounting /dev/mmcblk0p2 with -o defaults
[    5.466096] EXT4-fs (mmcblk0p2): mounted filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b r/w with ordered data mode. Quota mode: none.
[    5.562939] dracut: Mounted root filesystem /dev/mmcblk0p2
[    5.900654] dracut: Switching root
```

ugrd boot:
```
[    3.106379] Freeing unused kernel memory: 4864K
[    3.108254] Run /init as init process
[    3.109895]   with arguments:
[    3.109902]     /init
[    3.109909]     recovery
[    3.109915]   with environment:
[    3.109921]     HOME=/
[    3.109927]     TERM=linux
[    3.144962] mmc0: host does not support reading read-only switch, assuming write-enable
[    3.150951] mmc0: Host Software Queue enabled
[    3.152676] mmc0: new high speed SDHC card at address aaaa
[    3.156096] mmcblk0: mmc0:aaaa SL16G 14.8 GiB
[    3.165547] mmc1: new high speed SDIO card at address 0001
[    3.168096]  mmcblk0: p1 p2
[    3.170596] mmcblk0: mmc0:aaaa SL16G 14.8 GiB (quirks 0x00004000)
[    3.177101] usb 1-1: new high-speed USB device number 2 using dwc_otg
[    3.179132] Indeed it is in host mode hprt0 = 00001101
[    3.385638] usb 1-1: New USB device found, idVendor=0424, idProduct=9514, bcdDevice= 2.00
[    3.389224] usb 1-1: New USB device strings: Mfr=0, Product=0, SerialNumber=0
[    3.392200] hub 1-1:1.0: USB hub found
[    3.394433] hub 1-1:1.0: 5 ports detected
[    3.685123] usb 1-1.1: new high-speed USB device number 3 using dwc_otg
[    3.793618] usb 1-1.1: New USB device found, idVendor=0424, idProduct=ec00, bcdDevice= 2.00
[    3.797330] usb 1-1.1: New USB device strings: Mfr=0, Product=0, SerialNumber=0
[    3.802269] smsc95xx v2.0.0
[    3.899272] SMSC LAN8700 usb-001:003:01: attached PHY driver (mii_bus:phy_addr=usb-001:003:01, irq=184)
[    3.904286] smsc95xx 1-1.1:1.0 eth0: register 'smsc95xx' at usb-3f980000.usb-1.1, smsc95xx USB 2.0 Ethernet, b8:27:eb:0c:d0:4b
[    4.427679] EXT4-fs (mmcblk0p2): mounted filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b ro with ordered data mode. Quota mode: none.
[    4.544220] EXT4-fs (mmcblk0p2): unmounting filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b.
[    4.687024] EXT4-fs (mmcblk0p2): mounted filesystem 3b614a3f-4a65-4480-876a-8a998e01ac9b ro with ordered data mode. Quota mode: none.
[    4.813752] UGRD completed
```

> Multiple tests were performed, boot timed did not deviate by more than half a second
> Tests where undervoltages were reported were ignored, but none were detected in ugrd runs
