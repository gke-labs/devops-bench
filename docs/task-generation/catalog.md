# DevOps Bench — Expert Task Catalog

This is the **source of truth** for the task suite. Each row maps to one
`task.yaml` via the [generation methodology](./methodology.md). Rows are numbered
top-to-bottom; `task_id = 1000 + row#` (stable & idempotent).

- **Generation status** is tracked in [§ Generation status](#generation-status).
- To generate a task from a row, follow the
  [methodology](./methodology.md) (summarized for agents in [`AGENTS.md`](../../AGENTS.md)).

---

## Catalog

| # | Task Name | Description | Sample Prompt | Success Metric | Category | Difficulty |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | Debug CrashLoop | Investigate a failing container. | "Why is my 'frontend' pod in CrashLoopBackOff? Show me logs." | Root cause (e.g., env var missing) identified. | Dev | Easy |
| 2 | Log Aggregation | Query logs from multiple pods. | "Search for 'error' in all pods labeled 'app=gateway' in the last hour." | Filtered log output provided. | Dev | Hard |
| 3 | Trace Latency | Find where a request is slowing down. | "Use Cloud Trace to find why this GKE service is taking 5 seconds." | Trace waterfall shows the slow span. | Dev | Complex |
| 4 | VPA in Recommender Mode | Get resource advice for a pod. | "Set up Vertical Pod Autoscaler to just give recommendations." | kubectl get vpa shows 'Target' values. | Dev | Hard |
| 5 | Standard PVC | Request 5Gi of SSD storage. | "Create a 5Gi PVC using the 'premium-rwo' storage class." | PVC status is Bound. | Dev | Easy |
| 6 | Volume Expansion | Resize an existing 10Gi volume to 20Gi. | "Update my PVC to 20Gi without deleting the pod." | kubectl get pvc reflects new size. | Dev | Hard |
| 7 | Basic Secret | Create a secret from a literal value. | "Create a secret named 'db-pass' with value 'password123'." | kubectl get secret exists. | Dev | Easy |
| 8 | Secrets via CSI Store | Sync GCP Secret Manager to GKE pods. | "Mount a GCP Secret Manager secret into my pod as a volume." | File exists inside container at mount path. | Dev | Hard |
| 9 | ClusterIP Service | Expose a deployment internally. | "Create a Service for my app on port 80." | kubectl get svc shows internal IP. | Dev | Easy |
| 10 | NodePort Service | Expose an app on a specific node port. | "Expose my 'web' deployment on port 30001." | App accessible via <NodeIP>:30001. | Dev | Easy |
| 11 | Basic Ingress | Create a rule to route /api to a backend. | "Write an Ingress YAML for path /api to service 'api-svc'." | kubectl get ingress shows host/path. | Dev | Easy |
| 12 | Create Basic Deployment | Create a deployment with 3 replicas of Nginx. | "Generate a YAML for an nginx deployment with 3 replicas on port 80." | kubectl get deploy shows 3/3 ready. | Dev | Easy |
| 13 | Set Resource Limits | Add CPU/Mem requests and limits to an existing pod spec. | "Update this YAML to limit CPU to 500m and memory to 512Mi." | Pod describes correct resources section. | Dev | Easy |
| 14 | Configure Readiness Probe | Add a health check to a deployment. | "Add a readiness probe to my app on path /health at port 8080." | kubectl describe shows probe configured. | Dev | Easy |
| 15 | CronJob Setup | Create a job that runs every hour to clean a DB. | "Write a CronJob YAML that runs every hour using alpine." | kubectl get cronjob shows valid schedule. | Dev | Easy |
| 16 | StatefulSet with Volume | Deploy a 3-node MongoDB with persistent storage. | "Create a StatefulSet for MongoDB with a 10Gi volume claim." | PVCs are automatically provisioned. | Dev | Hard |
| 17 | Rolling Update Strategy | Configure a canary-like rollout with maxUnavailable. | "Modify my deployment to ensure 0 downtime with 25% maxSurge." | strategy.rollingUpdate is correctly set. | Dev | Hard |
| 18 | Sidecar Injection | Add a logging sidecar to a primary container. | "Add a fluent-bit sidecar to this deployment YAML." | Pod contains two containers in spec. | Dev | Hard |
| 19 | InitContainer Logic | Set up a container to run DB migrations before start. | "Add an initContainer to wait for the mysql service to be ready." | Pod waits for init to finish before main app. | Dev | Hard |
| 20 | HPA Configuration | Scale pods based on 70% CPU utilization. | "Configure Horizontal Pod Autoscaler for my web-app." | kubectl get hpa shows target 70%. | Dev | Hard |
| 21 | Blue/Green via Service | Switch traffic between two deployment versions. | "Write a script to flip the service selector from v1 to v2." | Service endpoint IP points to v2 pods. | Dev | Complex |
| 22 | Graceful Shutdown | Implement preStop hooks and terminationGracePeriod. | "Handle SIGTERM by adding a 30s sleep in a preStop hook." | Pod logs show graceful exit during deletion. | Dev | Complex |
| 23 | Gateway API Multi-Service | Route traffic to 'blue' or 'green' svc based on header version. | "Using Gateway API, route traffic to 'blue-svc' if header 'x-version' is 'v1'." | HTTPRoute with matches.headers correctly configured. | Dev | Hard |
| 24 | Custom Health Check Path | Override default LB health check for a GKE Service. | "My app health check is on /status:8081. Configure GKE BackendConfig to use this for the LB." | BackendConfig healthCheck spec matches app port/path. | Dev | Hard |
| 25 | Seccomp Profile App | Apply a custom seccomp profile to a high-security container. | "Generate a pod spec that uses a custom seccomp profile stored in /var/lib/kubelet/seccomp/." | securityContext.seccompProfile is correctly set to 'Localhost'. | Dev | Hard |
| 26 | Vulnerability Scanning Fix | Respond to a 'Critical' CVE in a running GKE image. | "Container Analysis found CVE-XXXX in my image. Provide a plan to patch and rollout without downtime." | Plan includes image rebuild, digest update, and rolling restart. | Dev | Hard |
| 27 | Filestore Multishare | Mount multiple shares from one Filestore instance. | "Configure GKE to use the Filestore CSI driver to mount two different shares on one pod." | Pod spec shows two volume mounts from the same StorageClass. | Dev | Hard |
| 28 | Local SSD for Scratch | Use Local SSDs for high-IOPS ephemeral storage. | "Configure a GKE node pool with Local SSDs and mount them in a pod for cache." | Pod uses hostPath or Local volume pointing to the SSD mount. | Dev | Hard |
| 29 | StatefulSet Scale Down | Safely scale down a Kafka cluster without data loss. | "Provide a script/plan to scale a 5-node Kafka StatefulSet to 3 nodes." | Plan includes data rebalancing (e.g., using Cruise Control) before K8s scale. | Dev | Complex |
| 30 | Managed Prometheus (GMP) | Scrape app metrics without installing a full Prometheus stack. | "Configure GKE Managed Service for Prometheus to scrape my /metrics endpoint on port 9090." | PodMonitoring resource created; metrics visible in Cloud Monitoring. | Dev | Hard |
| 31 | Distributed Tracing | Link a GKE frontend and backend in Cloud Trace. | "Add OpenTelemetry instrumentation to my Go app to send traces to Google Cloud Trace." | Traces show span parent-child relationships across services. | Dev | Complex |
| 32 | Dashboard for HPA | Visualize HPA scaling events vs. CPU usage. | "Create a Cloud Monitoring dashboard that shows HPA replicas vs. actual CPU utilization." | Dashboard JSON or UI steps provided. | Dev | Hard |
| 33 | Autopilot Compute Classes | Use 'Scale-Out' or 'Performance' classes in Autopilot. | "My Autopilot workload needs high-performance local SSD. How do I request it?" | Deployment includes cloud.google.com/compute-class: "Performance". | Dev | Hard |
| 34 | Pre-emptible Node Drain | Implement a 30s warning handler for Spot VM termination. | "How do I ensure my app gracefully shuts down when a GKE Spot node is reclaimed?" | Pod uses a termination handler to catch the Metadata Server signal. | Dev | Complex |
| 35 | Troubleshoot ImagePullBackOff | Debug an image pull error due to GCR/AR permissions. | "My pod is stuck in ImagePullBackOff for a private Artifact Registry image. How do I fix it?" | Identifies missing roles/artifactregistry.reader on the GKE node service account. | Dev | Easy |
| 36 | Zombie Process Cleanup | Debug a pod that has 100s of "defunct" processes. | "My pod has hundreds of <defunct> processes. How do I fix the PID 1 problem in my Dockerfile?" | Suggests using tini as an entrypoint or shareProcessNamespace. | Dev | Hard |
| 37 | Cloud Build GKE Deploy | Create a pipeline to build an image and update a deployment. | "Write a cloudbuild.yaml that builds a Docker image and runs 'gcloud clusters get-credentials'." | YAML uses gcr.io/cloud-builders/gke-deploy or kubectl. | Dev | Easy |
| 38 | Canary Deployment (Istio) | Shift 10% of traffic to version 'v2' using Istio. | "Generate an Istio VirtualService to split traffic 90/10 between v1 and v2 subsets." | VirtualService with weighted destinations is generated. | Dev | Hard |
| 39 | Standard to Autopilot | Convert a Standard GKE deployment to work on Autopilot. | "My deployment uses a HostPath volume. How do I change this to work on GKE Autopilot?" | Suggests PersistentVolumeClaim or EmptyDir (since HostPath is blocked). | Dev | Hard |
| 40 | Monolith Decomposition | Identify service boundaries for a legacy GKE app. | "This 5000-line YAML is a monolith. How should I split it into microservices?" | Suggests logic for Service per domain, NetworkPolicies, and ConfigMaps. | Dev | Complex |
| 41 | TCP Optimization | Tune sysctl parameters for a high-concurrency pod. | "How do I increase the max TCP connections (somaxconn) for an Nginx pod in GKE?" | Uses a securityContext with sysctls or an initContainer. | Dev | Hard |
| 42 | Node Anti-Affinity | Ensure two replicas of a DB never run on the same node. | "Write a podAntiAffinity rule to spread my 'redis' pods across different nodes." | podAntiAffinity with requiredDuringScheduling... is used. | Dev | Hard |
| 43 | Check Node Pressure | See why pods won't schedule. | "List all nodes with memory pressure." | kubectl get nodes shows pressure condition. | Platform | Easy |
| 44 | MTU Mismatch Debug | Resolve networking issues across VPCs. | "Debug packet loss between GKE and an on-prem VM." | MTU/MSS clamping recommendation provided. | Platform | Complex |
| 45 | Spot VM Node Pool | Create a node pool using Spot instances. | "Add a new node pool to my GKE cluster using Spot VMs." | kubectl get nodes shows spot instance labels. | Platform | Easy |
| 46 | Cost Allocation Labels | Tag workloads for billing breakdown. | "Add a 'team: mobile' label to all pods in the 'mobile' namespace." | GCP Billing export shows the cost label. | Platform | Hard |
| 47 | Right-sizing Audit | Identify over-provisioned pods. | "Find all pods where CPU usage is < 10% of their request." | List of underutilized pods generated. | Platform | Complex |
| 48 | Cluster Autoscaler Tuning | Prevent node deletion for specific pods. | "Annotate a pod so the cluster autoscaler doesn't evict it." | safe-to-evict: false annotation applied. | Platform | Complex |
| 49 | StorageClass Creation | Define a new class for Filestore. | "Create a StorageClass for GKE Filestore (NFS)." | kubectl get sc shows the new class. | Platform | Hard |
| 50 | Backup for GKE | Configure a backup plan for a namespace. | "Set up a Backup for GKE plan for my 'production' namespace." | BackupPlan resource is active in GCP. | Platform | Complex |
| 51 | Snapshot Restore | Recover a volume from a CSI snapshot. | "Create a new PVC from an existing VolumeSnapshot." | New pod mounts data from the snapshot. | Platform | Complex |
| 52 | View-Only RBAC | Create a role for viewing logs/pods only. | "Create a ClusterRole for a developer to only 'get' and 'list' pods." | auth can-i returns yes for list, no for delete. | Platform | Easy |
| 53 | Namespace Isolation | Create a namespace for a specific team. | "Create a namespace 'team-alpha' with a resource quota." | Namespace and ResourceQuota exist. | Platform | Easy |
| 54 | Workload Identity Bind | Link a K8s SA to a GCP SA. | "Configure Workload Identity for K8s SA 'myapp' to GCP SA 'gcp-app'." | Pod can access GCS without local keys. | Platform | Hard |
| 55 | Pod Security Standards | Enforce 'Baseline' security profile. | "Configure the namespace 'dev' to enforce the baseline pod security." | Privileged pods are rejected in that NS. | Platform | Hard |
| 56 | Binary Authorization | Only allow signed images to run. | "Enable Binary Authorization on my GKE cluster." | Unsigned images trigger a 'Forbidden' error. | Platform | Complex |
| 57 | KMS Secret Encryption | Encrypt ETCD secrets using a Cloud KMS key. | "Enable Application-layer Secrets Encryption on my cluster." | Cluster config shows database.encryptionConfig. | Platform | Complex |
| 58 | RBAC Troubleshooting | Debug why a service account cannot list nodes. | "Check why SA 'test' in 'default' can't view node list." | Correct RoleBinding identified and fixed. | Platform | Complex |
| 59 | Internal Load Balancer | Create a GCP ILB via annotations. | "Expose my service using a GKE internal load balancer." | Service type is LB with internal IP. | Platform | Hard |
| 60 | SSL via Managed Certs | Use Google-managed SSL for an Ingress. | "Configure my GKE ingress to use a Google Managed Certificate." | ManagedCertificate resource exists and is bound. | Platform | Hard |
| 61 | NetworkPolicy: Deny All | Isolate a namespace from all traffic. | "Create a NetworkPolicy to deny all ingress to namespace 'prod'." | Traffic to 'prod' pods times out. | Platform | Hard |
| 62 | Gateway API Setup | Implement a Gateway for multi-service routing. | "Generate a Gateway and HTTPRoute for two different services." | kubectl get httproute shows valid parents. | Platform | Hard |
| 63 | Cloud Armor Integration | Attach a WAF policy to a GKE Ingress. | "Add a Google Cloud Armor policy to my GKE frontend service." | BackendConfig references a security policy. | Platform | Complex |
| 64 | Multi-Cluster Ingress | Route traffic across two GKE clusters. | "Set up a MultiClusterIngress for a global web app." | MCI resource status shows healthy backends. | Platform | Complex |
| 65 | Service Mesh (ASM) | Enable sidecar injection for a namespace. | "Enable Anthos Service Mesh for the 'billing' namespace." | New pods in namespace have istio-proxy. | Platform | Complex |
| 66 | Pod Disruption Budget | Ensure high availability during node maintenance. | "Create a PDB for my 'frontend' app to keep 80% available." | kubectl get pdb shows minAvailable set. | Platform | Hard |
| 67 | Multi-Arch Deployment | Support both x86 and ARM nodes in one deployment. | "Update this spec to run on either ARM or x86 nodes." | nodeAffinity includes multiple arch terms. | Platform | Complex |
| 68 | PriorityClass Setup | Ensure critical pods preempt lower priority ones. | "Create a PriorityClass for system-critical apps." | priorityClassName is applied to critical pods. | Platform | Complex |
| 69 | HTTP-to-HTTPS Redirect | Configure a GKE Ingress to automatically redirect port 80 to 443. | "Create a FrontendConfig to force HTTPS redirect and link it to my Ingress." | FrontendConfig exists; Ingress annotation networking.gke.io/v1beta1.FrontendConfig is set. | Platform | Hard |
| 70 | Shared VPC Deployment | Deploy GKE in a Service Project using a Host Project's VPC. | "Write the gcloud command to create a GKE cluster in a shared VPC with specific subnets." | Command includes --network and --subnetwork pointing to host project. | Platform | Hard |
| 71 | Private Service Connect | Connect GKE to a managed service via PSC. | "Configure a GKE service to be reachable via a Private Service Connect endpoint." | Service attachment and DNS entries correctly defined. | Platform | Complex |
| 72 | Multi-Cluster Service (MCS) | Export a service from Cluster A to be discoverable in Cluster B. | "Generate the ServiceExport and ServiceImport YAMLs for cross-cluster communication." | ServiceExport status shows 'Exported'. | Platform | Complex |
| 73 | Cloud Armor Bot Mgmt | Implement bot management on a GKE Ingress. | "Add a Google Cloud Armor security policy to my GKE ingress to block known bots." | BackendConfig references a security policy with botManagement rules. | Platform | Complex |
| 74 | ExternalDNS Setup | Auto-sync GKE Ingress hosts to Cloud DNS. | "Configure ExternalDNS to create 'A' records in Cloud DNS for my GKE Ingress resources." | DNS records automatically appear in Cloud DNS after Ingress creation. | Platform | Hard |
| 75 | Cilium Network Policy | Use L7 (HTTP) filtering in GKE Dataplane V2. | "Create a NetworkPolicy that only allows GET requests to /public in my 'frontend' namespace." | CiliumNetworkPolicy (or DPv2 equivalent) restricts specific HTTP verbs/paths. | Platform | Complex |
| 76 | Dual-Stack IPv6 | Enable IPv4/IPv6 dual-stack networking for a pod. | "Configure a GKE cluster and a Deployment to support dual-stack IPv6 networking." | Pod status.podIPs contains both IPv4 and IPv6 addresses. | Platform | Complex |
| 77 | Workload Identity Debug | Identify why a pod cannot access a GCS bucket. | "The pod using SA 'my-k8s-sa' is getting 403 Access Denied for GCS. Troubleshoot the WI bind." | Identifies missing IAM role on GCP SA or missing annotation on K8s SA. | Platform | Hard |
| 78 | Binary Auth Attestation | Only allow images signed by 'Cloud Build'. | "Create a Binary Authorization policy requiring a signature from a specific attestor." | Deployment fails if image is not signed by the designated attestor. | Platform | Complex |
| 79 | Policy Controller Guardrail | Prevent LoadBalancers without specific tags. | "Write a ConstraintTemplate to prevent Services of type LoadBalancer unless they have a 'cost-center' label." | kubectl apply of a non-compliant service is rejected by the webhook. | Platform | Complex |
| 80 | KMS Key Rotation Ops | Handle a GKE cluster when the KMS key is rotated. | "How do I update my GKE cluster after rotating the Cloud KMS key used for secret encryption?" | Correct sequence of gcloud container clusters update provided. | Platform | Hard |
| 81 | Role-Based Log Filtering | Limit what logs a specific developer can see in Log Explorer. | "Configure GCP IAM so developer 'X' can only see logs from namespace 'dev' in GKE." | IAM Log View definition with correct filter expression. | Platform | Hard |
| 82 | GKE Sandbox (gVisor) | Run an untrusted workload in a hardened sandbox. | "Configure a node pool and a pod to run using GKE Sandbox (gVisor)." | Pod has runtimeClassName: gvisor. | Platform | Hard |
| 83 | FIPS 140-2 Compliance | Enable FIPS-validated modules for GKE nodes. | "How do I ensure my GKE node pools are FIPS 140-2 compliant?" | Command uses --enable-fips flag or specific FIPS-enabled OS images. | Platform | Complex |
| 84 | Automated Secret Rotation | Rotate DB secrets using Berglas or External Secrets Operator. | "Set up External Secrets Operator to sync a Cloud Secret Manager secret to K8s every 1h." | ExternalSecret resource created; K8s secret updates when GCP secret changes. | Platform | Hard |
| 85 | Regional PD Failover | Configure a DB to use Regional Persistent Disks. | "Create a StorageClass for Regional PDs that replicate across us-central1-a and us-central1-b." | replication-type: regional-pd in SC; PVC exists in two zones. | Platform | Hard |
| 86 | Volume Snapshot Schedule | Auto-snapshot a DB volume every night at 2 AM. | "Create a VolumeSnapshotClass and a schedule to backup my PVCs daily." | VolumeSnapshot objects created automatically according to schedule. | Platform | Hard |
| 87 | CSI Migration | Migrate from in-tree volume plugins to CSI driver. | "My old YAML uses 'gcePersistentDisk'. Convert it to use the GCE PD CSI driver." | YAML updated to use csi: driver: pd.csi.storage.gke.io. | Platform | Hard |
| 88 | Cross-Project Storage | Access a Persistent Disk located in a different GCP project. | "Can my GKE cluster in Project A mount a disk from Project B? Explain how." | Correct answer regarding IAM permissions and gcloud compute disks add-iam-policy-binding. | Platform | Complex |
| 89 | Custom Log Parsing | Use Fluent Bit to parse JSON logs in GKE. | "My app logs JSON. How do I configure GKE's managed Fluent Bit to parse these fields?" | LogConfig or custom ConfigMap ensures logs appear as structured data in GCP. | Platform | Hard |
| 90 | SLO-Based Alerting | Create an alert for "99.9% of requests < 200ms". | "Set up a Cloud Monitoring alert for a GKE service based on a Latency SLO." | Alert policy exists with the correct MQL or filter expression. | Platform | Complex |
| 91 | Node Problem Detector | Alert when a node has a 'KernelDeadlock'. | "How do I use Node Problem Detector in GKE to trigger an automated node drain?" | Remediation controller (like Draino) or logic identified for the event. | Platform | Complex |
| 92 | Cost Metering Breakdown | See exactly how much 'Namespace A' costs. | "Enable GKE Cost Allocation and query the BigQuery export for 'billing-namespace-a'." | SQL query provided that joins GKE metadata with billing data. | Platform | Hard |
| 93 | Terraform GKE Module | Create a cluster with private nodes and public master. | "Write a Terraform block for a GKE cluster with private nodes and a master authorized network." | TF code includes private_cluster_config and master_authorized_networks_config. | Platform | Hard |
| 94 | Blue/Green Cluster Upgrade | Upgrade GKE by creating a new cluster and shifting traffic. | "Write a workflow to migrate workloads from GKE 1.27 to 1.28 using a DNS flip." | Plan covers state migration (PVCs) and global LB updates. | Platform | Complex |
| 95 | Terraform Drift Repair | Fix a cluster that was manually edited in the GCP Console. | "Terraform plan shows changes I made in the console. How do I sync the state without deleting resources?" | terraform import or manual reconciliation steps provided. | Platform | Hard |
| 96 | Custom Machine Type | Use a non-standard CPU/Mem ratio for a node pool. | "Create a GKE node pool using custom machine types (e.g., 6 vCPUs, 42GB RAM)." | Command uses --machine-type with custom-6-43008. | Platform | Hard |
| 97 | Debug 502 Bad Gateway | Resolve 502s happening between GCLB and a GKE pod. | "I'm getting random 502 errors on my Ingress. Check the BackendConfig and pod health." | Recommends checking Keep-Alive timeout (must be > 600s for GCLB). | Platform | Hard |
| 98 | Resolve PDB Deadlock | Fix a scenario where a cluster cannot drain nodes due to PDBs. | "kubectl drain is hanging because of a PodDisruptionBudget. How do I safely bypass this?" | Recommends minAvailable: 0 or identifying the specific blocking pod. | Platform | Hard |
| 99 | Kernel OOM Investigation | Determine why a node is rebooting without a Pod OOM. | "A GKE node is crashing, but no pod shows OOMKill. How do I find the kernel log events?" | Command provided to use serial port logs or node-problem-detector. | Platform | Complex |
| 100 | Recover Deleted Namespace | Plan for recovering resources from a namespace deleted by mistake. | "Someone ran 'kubectl delete ns prod'. What are my options for recovery in GKE?" | Plan includes Backup for GKE restoration or rebuilding from GitOps/State. | Platform | Complex |
| 101 | Debug DNS Latency | Investigate 5-second delays in K8s DNS lookups. | "Our app has intermittent 5s DNS delays. Is this an ndots:5 issue? How do I verify?" | Identifies UDP packet drops or ndots search path overhead; suggests NodeLocal DNSCache. | Platform | Complex |
| 102 | Enforce Resource Limits | Use Gatekeeper to reject pods without CPU limits. | "Write a Constraint to ensure every pod in 'production' has a CPU limit set." | Valid YAML for a K8sMaxContainerLimits or similar constraint. | Platform | Hard |
| 103 | Audit Admin Activity | Find who changed a Service from ClusterIP to LoadBalancer. | "Search Cloud Logging to find the specific IAM user who modified service 'web-svc'." | Correct Log Explorer query: protoPayload.methodName="v1.compute.backendServices.patch". | Platform | Hard |
| 104 | Multi-Tenant Soft Isolation | Separate Team A and Team B on the same cluster. | "Configure namespaces and RBAC so Team A cannot see Team B's logs or pods." | Includes Namespaces, Roles, RoleBindings, and NetworkPolicies. | Platform | Complex |
| 105 | Automated Labeling Policy | Use a webhook to add 'owner' labels to all new pods. | "Generate a MutatingAdmissionWebhook to inject a default 'env' label into every pod." | Valid code for a mutating webhook or Policy Controller mutation. | Platform | Complex |
| 106 | Compliance Reporting | Generate a report of all 'Privileged' containers. | "List all containers in the cluster that are running in privileged mode or as root." | kubectl get pods -o jsonpath or gcloud query provided. | Platform | Hard |
| 107 | ArgoCD Sync Policy | Configure an app to auto-sync and prune deleted resources. | "Set up an ArgoCD Application spec for my GKE cluster with self-heal enabled." | syncPolicy includes automated, prune, and selfHeal. | Platform | Hard |
| 108 | Config Sync Setup | Sync GKE cluster state with a Git repository. | "Configure Config Sync on GKE to track a private GitHub repo using an SSH key." | RootSync resource and Secret for SSH key are correctly defined. | Platform | Hard |
| 109 | Blue/Green with Cloud Deploy | Use Google Cloud Deploy for a GKE delivery pipeline. | "Create a Cloud Deploy pipeline definition with 'dev', 'staging', and 'prod' targets." | DeliveryPipeline and Target YAMLs are syntactically correct. | Platform | Complex |
| 110 | Anthos Migrate (VM to K8s) | Draft a plan to containerize a legacy Linux VM. | "What are the steps to use Migrate to Containers to move a Java app on VM to GKE?" | Plan includes fit-and-finish check, image generation, and YAML creation. | Platform | Complex |
| 111 | Cross-Region Migration | Move a stateful workload from us-east1 to us-west1. | "How do I move a StatefulSet and its data from one GKE region to another?" | Plan uses VolumeSnapshots and regional replication strategies. | Platform | Complex |
| 112 | GPU Workload Setup | Deploy an L4 GPU node pool for ML inference. | "Create a GKE node pool with NVIDIA L4 GPUs and install the necessary drivers." | Command includes --accelerator and mentions the GPU driver installer. | Platform | Hard |
| 113 | Local SSD Raid 0 | Combine multiple local SSDs for maximum throughput. | "How do I configure a GKE node to RAID 0 three local SSDs for a data-intensive app?" | DaemonSet or startup-script logic provided to mount and strip disks. | Platform | Complex |
| 114 | Horizontal Pod Autoscaling (Custom Metrics) | Scale pods based on "Pub/Sub unacknowledged messages". | "Configure HPA to scale based on a custom metric from Stackdriver/Cloud Monitoring." | ExternalMetric source is correctly configured in the HPA YAML. | Platform | Complex |

---

## Generation status

`task_id = 1000 + #`. Provider dir per [methodology §2](./methodology.md#2-directory--naming-conventions);
class per [methodology §9](./methodology.md#9-task-classes--the-live-cluster-gap).
Rows not listed below are **pending generation**.

| # | task_id | Slug | Provider | Class | Generated | Last run / result |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | 1001 | debug-crashloop | generic | investigation | ✅ | MCP→kind, num_ctx 32768, env forwarded, judge gemma4-mcp:e2b (DEEPEVAL_DISABLE_TIMEOUTS=1). **e4b PASS: ChecklistScore 1.0** (all checks 1.0, OutcomeValidity 1.0, ToolInvocation 1.0) — listed pods then read logs → found DATABASE_URL root cause + fix. **e2b FAIL: ChecklistScore 0.25** — hallucinated pod name `frontend-xxxxx`, never reached logs. Clear capability contrast. Earlier infra fails: no-MCP tool-less; default num_ctx → empty; env not forwarded → "context does not exist". |
