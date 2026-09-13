# daily_image

Fetches a random portrait photo from Unsplash once a day, dithers it to the
E Ink **Spectra E6** six-colour palette (black, white, yellow, red, blue,
green), and uploads it as a PNG to a fixed object in a public GCS bucket —
so an e-paper frame can just poll one unchanging URL every morning.

Runs as a **Cloud Run Job** (batch semantics, no HTTP server, billed only
for the ~seconds it takes to run) triggered daily by **Cloud Scheduler**.

## How it works

1. `unsplash.py` calls `GET /photos/random?orientation=portrait` on the
   Unsplash API, then re-requests the photo's `raw` URL with
   `w=1200&h=1600&fit=crop&crop=entropy` query parameters so Unsplash's
   imgix backend returns an image already constrained to exactly
   1200x1600 — no client-side cropping needed. It also pings the photo's
   `download_location` endpoint, which Unsplash's API guidelines require
   whenever an image is downloaded for use.
2. `dither.py` Floyd-Steinberg dithers the image down to the 6 Spectra E6
   colours using `PIL.Image.quantize(palette=..., dither=FLOYDSTEINBERG)`.
3. `storage.py` saves the result as a PNG and uploads it to
   `gs://$GCS_BUCKET/$OBJECT_NAME` (default `latest.png`), overwriting the
   previous day's image so the public URL stays fixed:
   `https://storage.googleapis.com/$GCS_BUCKET/latest.png`.

### Palette calibration

E Ink publishes no numeric colour spec for Spectra 6, and the panel renders
each colour considerably more muted than pure primaries (community lab
measurements put red around `#a02020`-`#b21318`, yellow around
`#c1bb1e`-`#efde44`, depending on panel/batch/light — nowhere near `#ff0000`
/ `#ffff00`). Matching pixels against pure primaries directly, as an earlier
version of this file did, misclassifies a lot of mid-tone/muted pixels.

`dither.py`'s `SPECTRA_E6_PALETTE` uses those muted colours directly —
sourced from a [dithering tool built for this same 13.3" Spectra 6
panel](https://gist.github.com/quark-zju/e488eb206ba66925dc23692170ba49f9)
— as both the nearest-colour matching/Floyd-Steinberg target *and* the
encoded output pixel values. The panel's own ingestion pipeline nearest-
matches each pixel to a hardware ink channel itself, so there's no need to
re-encode to pure-primary codes here, and using the real muted values means
the PNG also previews faithfully on a computer screen.

A second independent source
([epdoptimize](https://github.com/Utzel-Butzel/epdoptimize), an e-paper
dithering library calibrated with lab equipment) measured comparable but
not identical muted values — panels vary by batch and viewing light, so
treat the defaults as a good approximation rather than ground truth. For
best fidelity, replace `SPECTRA_E6_PALETTE`'s tuples with values measured
from your own physical panel.

### Why PNG, not JPEG

The dithered image only contains 6 distinct colours. PNG is lossless, so
those exact colours (and the dither pattern itself) survive upload
untouched — no chroma-subsampling bleed at colour edges like JPEG would
introduce. It's also the smaller format here despite PNG usually losing
that comparison for photos: `dither.py` returns a palette-indexed ('P'
mode) image, so each pixel costs PNG only ~3 bits before compression,
whereas JPEG's DCT-based compression handles dithering's high-frequency
noise poorly and needs a larger file (or visible artefacts) to preserve it.

## Local run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export UNSPLASH_ACCESS_KEY=...
export GCS_BUCKET=...
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

python main.py
```

## Deploying to Google Cloud

Set some shell variables to keep the commands below copy-pasteable:

```bash
export PROJECT_ID=dexfieldpark
export REGION=us-central1
export BUCKET=dexfieldpark-daily-image     # must be globally unique
export REPO=daily-image
export JOB_NAME=daily-image

gcloud config set project "$PROJECT_ID"
```

The Unsplash access key is stored directly in Secret Manager rather than an
env var (see step 3) — never pass API keys on the command line where
they'd land in shell history.

### 1. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com
```

### 2. Create the public GCS bucket

Uniform bucket-level access + an `allUsers` IAM binding is the recommended
way to publish objects (rather than per-object ACLs):

```bash
gcloud storage buckets create "gs://$BUCKET" \
  --location="$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member=allUsers \
  --role=roles/storage.objectViewer
```

The image will then always be reachable at:
`https://storage.googleapis.com/$BUCKET/latest.png`

### 3. Store the Unsplash access key in Secret Manager

Create the secret and paste the key when prompted (keeps it out of shell
history and this terminal's scrollback):

```bash
gcloud secrets create unsplash-access-key \
  --replication-policy=automatic \
  --data-file=-
```

### 4. Build and push the container image

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION"

gcloud builds submit \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/daily-image:latest" .
```

### 5. Create a service account for the job

```bash
gcloud iam service-accounts create daily-image-job \
  --display-name="daily_image Cloud Run Job"

JOB_SA="daily-image-job@$PROJECT_ID.iam.gserviceaccount.com"

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$JOB_SA" \
  --role=roles/storage.objectAdmin

gcloud secrets add-iam-policy-binding unsplash-access-key \
  --member="serviceAccount:$JOB_SA" \
  --role=roles/secretmanager.secretAccessor
```

### 6. Create the Cloud Run Job

```bash
gcloud run jobs create "$JOB_NAME" \
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/daily-image:latest" \
  --region="$REGION" \
  --service-account="$JOB_SA" \
  --set-env-vars="GCS_BUCKET=$BUCKET,IMAGE_WIDTH=1200,IMAGE_HEIGHT=1600,OBJECT_NAME=latest.png" \
  --set-secrets="UNSPLASH_ACCESS_KEY=unsplash-access-key:latest" \
  --max-retries=1 \
  --task-timeout=300
```

Test it manually before scheduling:

```bash
gcloud run jobs execute "$JOB_NAME" --region="$REGION" --wait
```

### 7. Schedule it to run daily

Cloud Scheduler triggers the job by calling the Cloud Run Jobs REST `run`
endpoint, authenticated with an OIDC token from a dedicated invoker service
account:

```bash
gcloud iam service-accounts create daily-image-scheduler \
  --display-name="daily_image Cloud Scheduler invoker"

SCHEDULER_SA="daily-image-scheduler@$PROJECT_ID.iam.gserviceaccount.com"

gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --region="$REGION" \
  --member="serviceAccount:$SCHEDULER_SA" \
  --role=roles/run.invoker

gcloud scheduler jobs create http daily-image-trigger \
  --location="$REGION" \
  --schedule="0 6 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run" \
  --http-method=POST \
  --oauth-service-account-email="$SCHEDULER_SA"
```

This runs the job once a day at 06:00 UTC — adjust `--schedule` /
`--time-zone` as needed. Cloud Scheduler retries the trigger automatically
according to its default retry policy if the initial invocation fails.

## Environment variables

| Variable               | Required | Default      | Purpose                                             |
|-------------------------|----------|--------------|------------------------------------------------------|
| `UNSPLASH_ACCESS_KEY`   | yes      | —            | Unsplash API client ID                                |
| `GCS_BUCKET`            | yes      | —            | Destination bucket name                                |
| `IMAGE_WIDTH`           | no       | `1200`       | Output width in pixels                                 |
| `IMAGE_HEIGHT`          | no       | `1600`       | Output height in pixels                                 |
| `OBJECT_NAME`           | no       | `latest.png` | Fixed object name (keeps the public URL stable)         |
| `ARCHIVE_OBJECTS`       | no       | `false`      | If `true`, also stores a dated copy under `archive/`      |
| `UNSPLASH_QUERY`        | no       | (unset)      | Optional Unsplash search term to bias photo selection      |
