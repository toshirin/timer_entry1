# ops web

Local dashboard for `timer_entry_ops`.

## Docker

Run from the repository root:

```bash
docker run --rm \
  --name timer-entry-ops-web \
  --init \
  --entrypoint /bin/bash \
  -p 3000:3000 \
  -v "$PWD/ops/web:/app" \
  -v "$HOME/.aws:/root/.aws:ro" \
  -w /app \
  -e AWS_PROFILE \
  -e AWS_REGION=ap-northeast-1 \
  -e OPS_DB_CLUSTER_ARN='...' \
  -e OPS_DB_SECRET_ARN='...' \
  -e OPS_DB_NAME=timer_entry_ops \
  -e OPS_WEB_SCHEMA=ops_demo \
  node:22-bullseye \
  -lc "npm install && npm run dev"
```

Open `http://localhost:3000`.

Use `OPS_WEB_SCHEMA=ops_main` to view production data.

Docker 経由では `r` が効かないことがあります。
停止できない場合は別ターミナルから以下を実行します。

```bash
docker stop timer-entry-ops-web
```

## Asset config

Asset PnL uses an optional local config file at `ops/web/config/dashboard.json`.
Copy `ops/web/config/dashboard.example.json` and set the initial equity and annual manual trade adjustments.

`dashboard.json` is ignored by git.
Set `OPS_DASHBOARD_CONFIG_PATH` to read the config from another path.
