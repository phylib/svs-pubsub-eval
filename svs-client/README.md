# Clients for SVS Pub-Sub evaluation

## Install

```bash
cmake .
make
```

## Run

Register multicast prefix:

```bash
nfdc strategy set /ndn/svs /localhost/nfd/strategy/multicast
```

Start NFD and then start the clients

```bash
./SVSClient /platoon1/unit3
./SVSClient /platoon2/unit4
```

Every client listens to:
- `/ndn/svs`.. sync group prefix
- `/<prefix>/ndn/svs/`.. prefix for SVS Data packets named with seq-no
- `/<prefix>/ndn/svs/mapping`.. prefix for retrieving mapping data
- `/position`.. Data prefix of Position data packets
- `/voice`.. Data prefix of voice data packets

Voice and Position data packets are served under the following names:
-  `/voice/<prefix>/<timestamp>/v=0/s=<segement>`.. First segment is synced over SVS Pub/Sub, other segments retrieved using interest-data exchange
-  `/position/<prefix>/<timestamp>`.. should not be required, since synced over SVS Pub/Sub