import os
import sys
import argparse
import json

from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


from deployers.factory import get_deployer

def main():
    parser = argparse.ArgumentParser(description="DevOps Bench Infra Manager")
    parser.add_argument(
        "--use-terraform", action="store_true", help="Use Terraform for deployment"
    )
    parser.add_argument(
        "--stack",
        help="Infrastructure stack to use (e.g., prebuilt/minimum)",
        dest="stack"
    )
    # Support both --stack and deprecated --env for a smoother transition
    parser.add_argument("--env", help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(
        dest="provider", required=True, help="Cloud provider"
    )

    # GCP Subparser
    gcp_parser = subparsers.add_parser("gcp", help="GCP operations")
    gcp_subparsers = gcp_parser.add_subparsers(
        dest="action", required=True, help="Action"
    )

    # Add actions for GCP
    for action in ["up", "down", "info"]:
        p = gcp_subparsers.add_parser(action, help=f"Perform {action}")
        p.add_argument("--project", help="GCP Project ID")
        p.add_argument("--cluster-name", help="Name of the cluster")
        p.add_argument(
            "--location", help="GCP Location (Zone or Region)"
        )

        # Support deprecated --zone for transition
        p.add_argument("--zone", help=argparse.SUPPRESS)

    # KinD Subparser
    kind_parser = subparsers.add_parser("kind", help="KinD local operations")
    kind_subparsers = kind_parser.add_subparsers(
        dest="action", required=True, help="Action"
    )

    # Add actions for KinD
    for action in ["up", "down", "info"]:
        p = kind_subparsers.add_parser(action, help=f"Perform {action}")
        p.add_argument("--cluster-name", help="Name of the local KinD cluster")

    args = parser.parse_args()

    # Handle deprecated arguments
    stack = args.stack or args.env
    location = getattr(args, 'location', None)
    if hasattr(args, 'zone') and args.zone:
         print(
             "Warning: --zone is deprecated. Use --location instead.",
             file=sys.stderr
         )
         location = args.zone


    if args.provider == "gcp":
        project = args.project or os.environ.get("GCP_PROJECT_ID")
        cluster_name = args.cluster_name or os.environ.get("GKE_CLUSTER_NAME")
        # Enforce GCP_LOCATION precedence
        final_location = (
            location or os.environ.get("GCP_LOCATION", "us-central1-a")
        )

        if not project or not cluster_name:

            print(
                "Error: Project and Cluster Name must be specified via flags or "
                "environment variables (GCP_PROJECT_ID, GKE_CLUSTER_NAME).",
                file=sys.stderr
            )
            sys.exit(1)

        infra_config = {
            "deployer": "terraform" if args.use_terraform else "kubetest2",
            "stack": stack,
        }
        deployer = get_deployer(
            infra_config, project, cluster_name, global_location=final_location
        )

        if args.action == "up":
            deploy_type = "Terraform" if args.use_terraform else "kubetest2"
            print(f"Bringing up infrastructure ({deploy_type})...")
            deployer.up()
        elif args.action == "down":
            print(f"Tearing down infrastructure...")
            deployer.down()
        elif args.action == "info":
            print(json.dumps(deployer.get_cluster_info(), indent=2))
        else:
            print(
                f"Critical Error: Unsupported action '{args.action}' "
                f"for provider 'gcp'",
                file=sys.stderr
            )
            sys.exit(1)
            
    elif args.provider == "kind":
        cluster_name = args.cluster_name or os.environ.get("KUBERNETES_CLUSTER_NAME", "devops-bench-kind")
        infra_config = {
            "deployer": "terraform",
            "stack": stack or "prebuilt/kind",
        }
        deployer = get_deployer(infra_config, "local-project", cluster_name)

        if args.action == "up":
            print(f"Bringing up local KinD cluster {cluster_name} (Terraform)...")
            deployer.up()
        elif args.action == "down":
            print(f"Tearing down local KinD cluster {cluster_name}...")
            deployer.down()
        elif args.action == "info":
            print(json.dumps(deployer.get_cluster_info(), indent=2))
        else:
            print(
                f"Critical Error: Unsupported action '{args.action}' "
                f"for provider 'kind'",
                file=sys.stderr
            )
            sys.exit(1)
    else:
        print(
            f"Critical Error: Unsupported provider '{args.provider}'",
            file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
