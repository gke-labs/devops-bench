#!/bin/bash
# Mock upgrade audit script that identifies deprecated API versions
echo "Scanning cluster for deprecated API usage..."
sleep 2

echo "WARN: Found deprecated API usage in existing manifests!"
echo "--------------------------------------------------------"
echo "Resource Type: Ingress"
echo "Name: legacy-ingress"
echo "API Version: networking.k8s.io/v1beta1"
echo "Recommendation: Update to networking.k8s.io/v1 before upgrading to GKE 1.29+"
echo "--------------------------------------------------------"
exit 1
