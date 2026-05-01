import os
import sys
import argparse

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from deployers.gcp.gcp_deployer import GCPDeployer

def main():
    parser = argparse.ArgumentParser(description="DevOps Bench Infra Manager")
    subparsers = parser.add_subparsers(dest="provider", required=True, help="Cloud provider")
    
    # GCP Subparser
    gcp_parser = subparsers.add_parser("gcp", help="GCP operations")
    gcp_subparsers = gcp_parser.add_subparsers(dest="action", required=True, help="Action")
    
    # Add actions for GCP
    for action in ["up", "down", "info"]:
        p = gcp_subparsers.add_parser(action, help=f"Perform {action}")
        p.add_argument("--project", help="GCP Project ID")
        p.add_argument("--cluster-name", help="Name of the cluster")
        p.add_argument("--zone", default="us-central1-a", help="GCP Zone")
            
    args = parser.parse_args()
    
    if args.provider == "gcp":
        project = args.project or os.environ.get("PROJECT_ID")
        cluster_name = args.cluster_name or os.environ.get("CLUSTER_NAME")
        zone = args.zone or os.environ.get("ZONE", "us-central1-a")
        
        if not project or not cluster_name:
            print("Error: Project and Cluster Name must be specified via flags or environment variables (PROJECT_ID, CLUSTER_NAME).", file=sys.stderr)
            sys.exit(1)
            
        deployer = GCPDeployer(project=project, zone=zone, cluster_name=cluster_name)
        
        if args.action == "up":
            print(f"Bringing up cluster {cluster_name}...")
            deployer.up()
        elif args.action == "down":
            print(f"Tearing down cluster {cluster_name}...")
            deployer.down()
        elif args.action == "info":
            import json
            print(json.dumps(deployer.get_cluster_info(), indent=2))
        else:
            print(f"Critical Error: Unsupported action '{args.action}' for provider 'gcp'", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Critical Error: Unsupported provider '{args.provider}'", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
