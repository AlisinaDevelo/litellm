# litellm Helm chart

Deploys [LiteLLM](https://github.com/BerriAI/litellm) from one image, `ghcr.io/berriai/litellm` (mirrored at `docker.litellm.ai/berriai/litellm`), in one of two layouts:

- componentized (default): the `gateway` (LLM data plane, port 4000), the `backend` (management API, port 4001) and the `ui` (static dashboard, port 3000) each get their own Deployment, Service, HPA and PDB so they scale independently
- monolith: `monolith.enabled: true` renders one Deployment and Service running the full proxy (`args: [proxy, ...]`), which serves the gateway routes, the management routes and the Admin UI from a single process

Both layouts run the same image. The image entrypoint dispatches on the first container argument (`proxy`, `gateway`, `backend`, `ui`, `migrations`, `metrics`, `collector`), so the chart only ever sets `args` and never `command`

## Requirements

Kubernetes 1.25+ and Helm 3.8+ (the dependencies are OCI charts). The proxy needs a PostgreSQL database, either your own through `database.writer.*` or the bundled Bitnami subchart with `postgresql.enabled: true` (evaluation only), and a master key, either an existing Secret named by `masterKey.secretName` or one the chart generates with `masterKey.generate: true`

## Install

```bash
helm dependency build helm/litellm
kubectl create secret generic litellm-master-key-secret --from-literal=master-key=sk-change-me
helm install litellm helm/litellm \
  --set database.writer.host=postgres.example.com \
  --set database.writer.dbname=litellm \
  --set database.writer.passwordSecret.name=litellm-db-secret
```

The image tag defaults to the chart's `appVersion`. Override it with `image.tag`, or pin the bytes with `image.digest`, which renders as `repository:tag@digest`

## Monolith quickstart

```bash
helm dependency build helm/litellm
helm install litellm helm/litellm \
  --set monolith.enabled=true \
  --set masterKey.generate=true \
  --set postgresql.enabled=true \
  --set postgresql.auth.password=change-me
kubectl port-forward svc/litellm-litellm 4000:4000
```

With `monolith.enabled: true`:

- one Deployment and one Service named `<release>-litellm` render, running `args: [proxy, --port, 4000, --config, /app/config/config.yaml]` plus `monolith.extraArgs`
- the gateway, backend and ui Deployments, Services, HPAs, PDBs and ServiceMonitors are not rendered, whatever `gateway.enabled`, `backend.enabled` and `ui.enabled` say
- every `gateway.*` value configures the monolith pod: `config`, `numWorkers`, `resources`, probes, `securityContext`, `hpa`, `keda`, `pdb`, `metricsServer`, `collector`, `volumes`, `extraEnv`, scheduling. The monolith runs as `serviceAccounts.gateway`
- every `backend.*` and `ui.*` value is ignored
- the Ingress sends every path, built in or from `ingress.extraPaths`, to the monolith Service
- the migrations Job renders exactly as in componentized mode

## Optional bundled datastores

`postgresql.enabled` and `redis.enabled` pull the Bitnami subcharts declared in `Chart.yaml` (Helm `condition:` gating, off by default). When on, the chart wires `DATABASE_*` and `REDIS_*` into every workload from the subchart Services and Secrets, so `database.writer.host` and `redis.host` must stay empty. The bundled images are pinned to `bitnamilegacy/*` tags; the render fails on an empty or `latest` PostgreSQL tag unless a digest is set

## Testing

```bash
helm dependency build helm/litellm
helm lint helm/litellm
helm unittest -f 'tests/*.yaml' helm/litellm
helm test <release> --logs
```

## Migrating from the litellm-helm chart

The `litellm-helm` chart (`oci://ghcr.io/berriai/litellm-helm`) is retired; its published packages stay available for a grace period. Its flat values described one monolith Deployment, so the equivalent install here is `monolith.enabled: true` with the values moved under `gateway.*`. The per-component `gateway.image`, `backend.image`, `ui.image` and `migrations.image` blocks of earlier `helm/litellm` versions are gone too: the chart is a major bump to `1.0.0` and every container uses the top-level `image`

| litellm-helm value | litellm value |
|---|---|
| (implicit single Deployment) | `monolith.enabled: true` |
| `image.repository` / `image.tag` / `image.pullPolicy` | `image.repository` / `image.tag` / `image.pullPolicy` (`image.digest` is new) |
| `replicaCount` | `gateway.replicaCount` |
| `args` | `monolith.extraArgs` (appended after the chart's proxy arguments) |
| `command` | removed: the image entrypoint dispatcher must stay in place |
| `proxy_config` | `gateway.config.proxy_config` |
| `proxyConfigMap.create: false` + `proxyConfigMap.name` | `gateway.config.create: false` and mount your ConfigMap with `gateway.volumes` / `gateway.volumeMounts`, or pass `--config` in `monolith.extraArgs` |
| `masterkeySecretName` / `masterkeySecretKey` | `masterKey.secretName` / `masterKey.secretKey` |
| `masterkeySecretName: ""` (auto generated Secret) | `masterKey.generate: true` with `masterKey.secretName: ""` |
| `db.useExisting`, `db.endpoint`, `db.database`, `db.secret.*` | `database.writer.host`, `database.writer.port`, `database.writer.dbname`, `database.writer.passwordSecret.*` |
| `db.readReplicaUrl` / `db.secret.readReplica*` | `database.reader.*` |
| `db.connectionPool.*` | `database.connectionPool.*` |
| `db.deployStandalone: true` | `postgresql.enabled: true` (plus `postgresql.auth.password`) |
| `postgresql.*` | `postgresql.*` (unchanged subchart values) |
| `redis.enabled: true` (bundled) | `redis.enabled: true` (bundled, unchanged subchart values) |
| external Redis via `envVars` | `redis.host`, `redis.port`, `redis.passwordSecret.*`, `redis.cluster` |
| `envVars` / `extraEnvVars` | `gateway.extraEnv` (list of `name` / `value` or `valueFrom` entries) |
| `environmentSecrets` | `gateway.envSecrets` |
| `environmentConfigMaps` | `gateway.envConfigMaps` |
| `logLevel` | `gateway.logLevel` |
| `resources` | `gateway.resources` |
| `livenessProbe` / `readinessProbe` / `startupProbe` | `gateway.livenessProbe` / `gateway.readinessProbe` / `gateway.startupProbe` |
| `securityContext` / `podSecurityContext` | `gateway.securityContext` / `gateway.podSecurityContext` |
| `service.*` | `gateway.service.*` |
| `ingress.*` | `ingress.*` (routes to the monolith Service in monolith mode) |
| `autoscaling.*` | `gateway.hpa.*` |
| `keda.*` | `gateway.keda.*` (`keda.prometheus.requestsPerSecond` / `tokensPerSecond` are `gateway.keda.prometheus.targetRequestsPerSecond` / `targetTokensPerSecond`) |
| `pdb.*` | `gateway.pdb.*` |
| `metricsServer.*` | `gateway.metricsServer.*` |
| `serviceMonitor.*` | `gateway.serviceMonitor.*` |
| `collector.*` | `gateway.collector.*` |
| `billingMetrics.*` | `billingMetrics.*` |
| `migrationJob.*` | `migrationJob.*` |
| `volumes` / `volumeMounts` | `gateway.volumes` / `gateway.volumeMounts` |
| `extraContainers` / `extraInitContainers` | `gateway.extraContainers` / `gateway.extraInitContainers` |
| `lifecycle` | `gateway.lifecycle` |
| `strategy` | `gateway.strategy` |
| `deploymentAnnotations` / `deploymentLabels` / `deploymentMinReadySeconds` | `gateway.deploymentAnnotations` / `gateway.deploymentLabels` / `gateway.minReadySeconds` |
| `podAnnotations` / `podLabels` | `gateway.podAnnotations` / `gateway.podLabels` |
| `nodeSelector` / `tolerations` / `affinity` / `topologySpreadConstraints` | `gateway.nodeSelector` / `gateway.tolerations` / `gateway.affinity` / `gateway.topologySpreadConstraints` |
| `terminationGracePeriodSeconds` | `gateway.terminationGracePeriodSeconds` |
| `serviceAccount.*` | `serviceAccounts.gateway.*` |
| `extraResources` | `extraResources` |
| `nameOverride: "litellm"` | `nameOverride: ""` (the chart name is already `litellm`) |

A minimal migration:

```yaml
monolith:
  enabled: true
masterKey:
  secretName: litellm-master-key-secret
database:
  writer:
    host: postgres.example.com
    dbname: litellm
    passwordSecret:
      name: litellm-db-secret
      usernameKey: username
      passwordKey: password
gateway:
  replicaCount: 2
  config:
    proxy_config:
      model_list:
        - model_name: gpt-4o
          litellm_params:
            model: openai/gpt-4o
            api_key: os.environ/OPENAI_API_KEY
  envSecrets:
    - litellm-provider-keys
```

The monolith Service keeps the `<release>-litellm` name the old chart produced through its `nameOverride: "litellm"` default, so an existing Ingress or port-forward keeps working after `helm uninstall` of the old release and `helm install` of this one. The generated master key Secret has `helm.sh/resource-policy: keep` and is reused across upgrades through `lookup`, matching the old chart
