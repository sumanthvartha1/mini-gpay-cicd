# Mini GPay

A payment app I built to learn Docker, CI/CD, and Kubernetes from scratch. The app lets users check balances, send money, and view transaction history — nothing fancy, but the infrastructure behind it covers real production patterns.

## What I built

Five containers working together — a Flask API backend, PostgreSQL database, Redis cache, static HTML frontend, and nginx as a reverse proxy. Everything orchestrated first with Docker Compose locally, then deployed through a Jenkins CI/CD pipeline to AWS.

```
browser → nginx (port 80) → routes /api to backend, / to frontend
                              backend → postgres (stores data)
                              backend → redis (caches balances)
```

## Architecture

<img width="1442" height="1040" alt="image" src="https://github.com/user-attachments/assets/4a75515e-afe1-45f9-88e4-66510ca58c47" />


Two separate Docker networks. The database sits on the backend network only — nginx and the frontend can never reach it directly. The backend bridges both networks. This is the same isolation pattern banks use in production.

## Tech stack

- **Backend:** Python, Flask, psycopg2, redis-py
- **Database:** PostgreSQL 15 (Alpine)
- **Cache:** Redis 7 (Alpine)
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Proxy:** Nginx (Alpine)
- **Containers:** Docker, Docker Compose
- **CI/CD:** Jenkins on AWS EC2
- **Registry:** AWS ECR
- **Orchestration:** Kubernetes (minikube for learning)
- **Cloud:** AWS (EC2, ECR, IAM)

## Project structure

```
mini-gpay/
├── Jenkinsfile               # CI/CD pipeline definition
├── docker-compose.yml        # local development setup
├── backend/
│   ├── Dockerfile
│   ├── app.py                # Flask API — 5 endpoints
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile
│   └── index.html            # payment UI
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf            # routing rules
├── postgres-init/
│   └── init.sql              # creates tables + sample data
└── k8s/
    ├── postgres.yaml         # deployment + PVC + service
    ├── redis.yaml            # deployment + service
    ├── backend.yaml          # deployment + service (pulls from ECR)
    ├── frontend.yaml         # deployment + service (pulls from ECR)
    └── nginx.yaml            # deployment + LoadBalancer service
```

## How to run locally

```bash
git clone https://github.com/sumanthvartha1/mini-gpay-cicd.git
cd mini-gpay-cicd
docker compose up --build
```

Open `http://localhost:80`. Select a user, send money, check history.

Stop: `docker compose down`

## API endpoints

```
GET  /api/users                → list all users
GET  /api/balance/:id          → get balance (checks Redis first, falls back to Postgres)
POST /api/send                 → transfer money (body: sender_id, receiver_id, amount)
GET  /api/transactions/:id     → transaction history for a user
GET  /api/health               → health check
```

Send money example:
```json
POST /api/send
{
    "sender_id": 1,
    "receiver_id": 2,
    "amount": 500
}
```

## CI/CD pipeline

Jenkins runs on an EC2 instance. The pipeline has 5 stages:

```
git push → Jenkins triggers
  │
  ├── 1. Checkout     — pulls latest code from GitHub
  ├── 2. Build        — docker build for backend, frontend, nginx
  ├── 3. Login        — authenticates to AWS ECR
  ├── 4. Push         — tags and pushes all 3 images to ECR
  └── 5. Cleanup      — removes dangling images
```

Every build tags images with the Jenkins build number (`:1`, `:2`, `:3`) and `:latest`. Rollback is just pointing to an older tag.

### Jenkins setup

- EC2 instance: Ubuntu 22.04, t2.medium
- Jenkins installed as systemd service on port 8080
- Docker installed, Jenkins user added to docker group
- AWS CLI configured with a dedicated `jenkins-ci` IAM user (ECR permissions only)
- Plugins: Docker Pipeline, AWS Steps, Git

### ECR repositories

```
gpay-backend    — Flask API image
gpay-frontend   — static HTML image
gpay-nginx      — nginx proxy image
```

PostgreSQL and Redis pull directly from Docker Hub — no ECR repos needed for official images.

## Kubernetes deployment

Deployed to minikube on the same EC2 instance. Five deployments, five services:

| Service    | Type           | Image source | Notes                          |
|------------|----------------|--------------|--------------------------------|
| postgres   | ClusterIP      | Docker Hub   | PVC for data, ConfigMap for init.sql |
| redis      | ClusterIP      | Docker Hub   | No persistent storage (cache)  |
| backend    | ClusterIP      | ECR          | Connects to postgres and redis by service name |
| frontend   | ClusterIP      | ECR          | Static HTML served by nginx    |
| nginx      | LoadBalancer   | ECR          | Single entry point             |

ECR authentication handled via `kubectl create secret docker-registry`. Token refreshed every 12 hours (ECR limitation — EKS handles this automatically in production).

### Deploy to Kubernetes

```bash
# create ECR secret
TOKEN=$(aws ecr get-login-password --region ap-south-2)
kubectl create secret docker-registry ecr-secret \
  --docker-server=ACCOUNT_ID.dkr.ecr.ap-south-2.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$TOKEN

# deploy everything
kubectl apply -f k8s/
```

## Things I learned building this

**Docker networking** — containers are isolated by default. Putting them on the same network lets them find each other by service name through Docker's built-in DNS. IP addresses change on restart, names don't.

**Layer caching matters** — copying requirements.txt before the code means pip install gets cached. Changed one line in app.py? Build goes from 3 minutes to 8 seconds. Across 20 deploys a day that adds up fast.

**Volumes vs bind mounts** — named volumes for database persistence (Docker manages the storage), bind mounts for development (edit code locally, container sees changes instantly).

**Health checks prevent race conditions** — without them, the backend starts before PostgreSQL is ready and crashes with "connection refused." With `condition: service_healthy`, the backend waits until pg_isready passes.

**Network isolation is real security** — two separate networks means even if nginx gets compromised, the attacker can't reach the database. The backend is the only bridge between networks.

**ECR tokens expire** — 12 hours. Pods go into ImagePullBackOff when the token dies. In production on EKS this is handled automatically. On minikube you refresh the secret manually.

**Minikube on cloud VMs has networking quirks** — NodePort binds to 127.0.0.1 by default, not 0.0.0.0. Docker Compose publishes to 0.0.0.0 by default. For a learning environment, Docker Compose on EC2 with ECR images is the most reliable deployment method.

**`--no-cache-dir` in pip install** — pip saves downloaded package files inside the image. Useless dead weight since pip never runs again. The flag removes them before the layer freezes.

**PGDATA subdirectory trick** — Kubernetes PersistentVolumes create a `lost+found` directory. PostgreSQL sees it and skips initialization. Setting `PGDATA=/var/lib/postgresql/data/pgdata` forces PostgreSQL to use a clean subdirectory.

## Cost

- EC2 t2.medium: ~$0.0464/hour (~$1.11/day)
- ECR storage: negligible for 3 small images
- Stop EC2 when not using it — only pays for 20GB EBS storage (~$0.10/month)

## What I'd do differently in production

- Use AWS EKS instead of minikube (proper networking, auto-scaling, managed control plane)
- Use AWS RDS instead of PostgreSQL in a container (managed backups, failover)
- Use Terraform to define all infrastructure as code
- Store secrets in AWS Secrets Manager, not environment variables in YAML
- Add HTTPS with a real domain and SSL certificate
- Add monitoring with Prometheus + Grafana
- Add GitHub webhooks to trigger Jenkins automatically on push
- Use Helm charts instead of raw Kubernetes YAML files
