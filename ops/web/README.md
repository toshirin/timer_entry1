# ops web

Local dashboard for `timer_entry_ops`.

## Docker

Run from the repository root:

```bash
docker run --rm \
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
