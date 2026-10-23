# Custom OpenTTD engine

M2 uses a narrow fork of OpenTTD 15.3. The current engine branch is
[`CaptainCucumber/OpenTTD:copilot/m2a-native-identity`](https://github.com/CaptainCucumber/OpenTTD/tree/copilot/m2a-native-identity),
commit `2850af59a5df2fe32aaff718b8e3dbb01808ecdd`, based directly on upstream
revision `14ec60f248547d4d062a1160f0fc26d742319888`.

The same change is retained as
[`patches/0001-Add-bounded-Copilot-identity-bridge.patch`](patches/0001-Add-bounded-Copilot-identity-bridge.patch).
It changes four existing Admin-network files and adds no build-system entry.

## Build

```sh
git clone --branch copilot/m2a-native-identity \
  https://github.com/CaptainCucumber/OpenTTD.git vendor/openttd-copilot-engine
cmake -S vendor/openttd-copilot-engine -B build/openttd-m2a \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DOPTION_DEDICATED=ON \
  -DOPTION_USE_ASSERTS=ON
cmake --build build/openttd-m2a --target openttd -j 8
```

The M2a binary is a dedicated build. The probe stages language, compatibility,
and base-set resources from the installed OpenTTD 15.3 application into a
disposable profile. It never uses the normal profile for execution.

## Boundary

Protocol version 1 adds one authenticated Admin request and response packet.
The request is accepted only after Admin authentication and only from an IPv4
or IPv6 loopback peer. It can return bounded world fields and either all valid
companies or one explicitly requested company. It cannot invoke RCON, execute
arbitrary code, or mutate the game.

M2b will add the first typed mutation through OpenTTD's normal game-thread
command validation. Do not extend the identity request into a generic command
transport.
