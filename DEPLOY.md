# Deploying WiFi Presence (Docker + Dockge)

This packages the app as a single Docker image, built by GitHub Actions and
published to the GitHub Container Registry (GHCR). Your Ubuntu server runs it as
a Dockge stack, and updates are a one-click pull in Dockge.

## One-time setup

### 1. Push the repo to GitHub
```bash
git remote add origin git@github.com:<your-username>/wifi_presence.git
git push -u origin master
```
A **public** repo keeps everything free and lets the server pull the image with
no login. (Private also works — see "Private image" at the bottom.)

### 2. Let CI build the first image
The included workflow (`.github/workflows/docker-publish.yml`) runs on every push
to `master`/`main`. After the first push, check the **Actions** tab — it builds
`ghcr.io/<owner>/wifi_presence:latest` and pushes it to GHCR. No secrets to set;
it uses the built-in `GITHUB_TOKEN`.

### 3. Make the image public (recommended)
On GitHub: your profile → **Packages** → `wifi_presence` → **Package settings** →
**Change visibility** → Public. Now the server can pull without authenticating.
(The image contains no secrets — your router password lives only in the runtime
data volume, never in the image.)

### 4. Create the stack in Dockge
In Dockge → **+ Compose** → name it `wifi-presence`, paste the contents of
[`compose.yaml`](compose.yaml), and **replace `OWNER`** with your GitHub
username (lowercase). Click **Deploy**.

Open `http://<server-ip>:8000`, go to **Settings**, enter your router SSH
details, hit **Test connection**, and you're live.

## Pushing updates — the everyday workflow

```
edit code  →  git push   →  GitHub Actions rebuilds :latest   →
   in Dockge: open the wifi-presence stack → click Update (pull) → done
```

Dockge's update pulls the new `:latest` image and recreates the container. Your
configuration and device mappings persist because they live in the
`wifi_presence_data` volume (mounted at `/data`), not in the image.

Equivalent on the CLI, if you ever want it:
```bash
docker compose pull && docker compose up -d
```

## Why host networking

The compose file uses `network_mode: host`. That's deliberate:
- the app can SSH to your **router and APs** on the LAN, and
- it sees each phone's **real IP**, which is what makes *Register this device* /
  the QR flow identify the right phone. With bridge networking every request
  would appear to come from the Docker gateway and auto-detect would break.

The app listens on `:8000` (change with the `PORT` env in the compose file).

## Data & backups

Everything that's hard to recreate lives in the `wifi_presence_data` volume:
`/data/wifi_presence.db` plus `/data/wifi-presence-config-backup.json` (an
auto-written, auto-restoring config backup). To back it up off-box:
```bash
docker run --rm -v wifi_presence_data:/data -v "$PWD":/out alpine \
  tar czf /out/wifi-presence-data.tgz -C /data .
```

## Optional: fully automatic updates (Watchtower)
If you'd rather updates land on their own a few minutes after each push, add a
Watchtower stack in Dockge:
```yaml
services:
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --cleanup --interval 300 wifi-presence
    restart: unless-stopped
```

## Private image (if you keep the repo private)
On the server, log Docker in to GHCR once with a Personal Access Token that has
`read:packages`:
```bash
echo <TOKEN> | docker login ghcr.io -u <your-username> --password-stdin
```
Then Dockge can pull the private image as normal.
