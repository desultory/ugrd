## How does UGRD compare to other generators?

### Run time

People say python is slow, but UGRD is very fast, even on slow hardware.

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

#### Compression

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

### Image size

ugrd makes very small images, even with no compression, it creates smaller images than dracut with zstd compression!

| Generator | Compression   | Size  | Mode     |
|-----------|---------------|-------|----------|
| dracut    | no            | 30M   | hostonly |
| dracut    | no            | 24M   | standard |
| dracut    | zstd          | 13M   | standard |
| dracut    | zstd          | 8.5M  | hostonly |
| ugrd      | no            | 9.41M | standard |
| ugrd      | xz (default)  | 2.64M | standard |

