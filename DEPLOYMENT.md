# Production Deployment Guide
## Smart Co-Working Space Management Using Real-Time Monitoring

This project is configured with zero-dependency native runtimes for instant multi-cloud deployment across **AWS**, **Vercel**, and **Netlify**.

---

## 1. Deploying to Vercel (Recommended for Instant Serverless)

The repository contains pre-configured `vercel.json` and `/api/index.py` serverless adapters.

### Option A: Using Vercel CLI
```bash
# 1. Install or run Vercel CLI
npx vercel

# 2. Deploy directly to production
npx vercel --prod
```

### Option B: Using GitHub Integration (Zero-Config)
1. Push this repository to GitHub or GitLab.
2. Go to [vercel.com](https://vercel.com/new).
3. Import the repository.
4. Set the Root Directory to `smart-coworking-space`.
5. Click **Deploy**. Vercel will automatically build the static assets from `/static` and bind the `/api` Python serverless endpoints.

---

## 2. Deploying to Netlify (Frontend & Edge CDN)

The repository includes `netlify.toml` pre-configured with asset caching rules and SPA fallback routing.

### Option A: Drag-and-Drop Instant Deploy (Zero CLI)
1. Navigate to [app.netlify.com/drop](https://app.netlify.com/drop).
2. Drag and drop the `smart-coworking-space/static` directory directly into the browser window.
3. Your web portal is instantly live on a custom `*.netlify.app` domain with free SSL/TLS!

### Option B: Netlify CLI
```bash
# 1. Install or run Netlify CLI
npx netlify-cli deploy --dir=static --prod
```

---

## 3. Deploying to AWS (App Runner, ECS, or Lightsail)

For long-lived persistent connections (Server-Sent Events streaming & background auto-release daemons), **AWS App Runner** or **AWS Lightsail Containers** is the enterprise standard.

### Option A: AWS App Runner (via Docker)
1. Build the production Docker image:
   ```bash
   docker build -t smart-coworking:latest .
   ```
2. Push to Amazon Elastic Container Registry (ECR):
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
   docker tag smart-coworking:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/smart-coworking:latest
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/smart-coworking:latest
   ```
3. In the AWS App Runner console, create a new service pointing to the container image on port `8000`. AWS automatically provides autoscaling, zero-downtime rolling updates, and managed HTTPS.

### Option B: AWS Elastic Beanstalk
1. The repository includes `Procfile` configured for Python web processes:
   ```
   web: python run.py
   ```
2. Deploy via EB CLI:
   ```bash
   eb init -p python-3.13 smart-coworking
   eb create smart-coworking-prod
   ```

---

## 4. Production Environment Configuration

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port on which the HTTP server listens |
| `HOST` | `0.0.0.0` | Bind IP (`0.0.0.0` for containers/cloud) |
| `COWORKING_SECRET_KEY` | *(Generated)* | Cryptographic salt used for signing JWT bearer tokens |

---

## 5. Health Checks & Verification

After deployment, test the health and data endpoints:
- **Web Portal**: `https://<YOUR_DEPLOYED_DOMAIN>/`
- **Spaces Health Endpoint**: `https://<YOUR_DEPLOYED_DOMAIN>/api/spaces`
- **Real-Time SSE Stream**: `https://<YOUR_DEPLOYED_DOMAIN>/api/telemetry/stream`
