# Getting the Track 1 data

You need one bundle: **`Market-cloudbed-1`**. It is a 1.3 GB download and about 12 GB
unpacked, so it is not in this repository. From `track-1/`:

```bash
curl -O https://mantisgrid-hackathon.s3.us-east-1.amazonaws.com/track-1-Market-cloudbed-1.zip
unzip track-1-Market-cloudbed-1.zip -d data
```

(Or open the link in a browser and unzip the file into `track-1/data/`.) You end up with:

```
track-1/data/Market-cloudbed-1/
├── telemetry/          metrics, logs and traces, one folder per day
├── query.csv           the cases you must answer
├── dev/query_dev.csv   the same cases WITH answers, so you can score yourself
└── manifest.json
```

Every `make` target in `track-1/` assumes that path.

**Do not use the original OpenRCA download.** It contains the answers to the cases
we evaluate on, and a submission that has seen them cannot be scored. This bundle
has the answers removed.
