# Deploying k8scost

`k8scost` ships a container and is deployable to any cloud or orchestrator.

| Target | How |
|---|---|
| **Docker Compose** | `docker compose -f deploy/docker-compose.yml up -d` |
| **Kubernetes** | `kubectl apply -f deploy/k8s.yaml` |
| **Terraform** | `cd deploy/terraform && terraform init && terraform apply` |
| **AWS** | ECS Fargate / App Runner / Lambda (container image) from `ghcr.io/cognis-digital/k8scost` |
| **Azure** | Container Apps / ACI: `az containerapp create --image ghcr.io/cognis-digital/k8scost` |
| **GCP** | Cloud Run: `gcloud run deploy k8scost --image ghcr.io/cognis-digital/k8scost` |
| **Fly.io / Render / Railway** | point at the Dockerfile |

CI publishes the image to GHCR on tag push (`.github/workflows/docker-publish.yml`).
