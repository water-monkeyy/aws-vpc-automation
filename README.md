# AWS VPC Automation

Production-style AWS VPC provisioning using **Python (boto3)** and **Terraform**.

Designed for zero manual console work, consistent environments, and safe teardown.

## Features
- Full VPC creation with DNS hostnames enabled
- Public and private subnets across multiple Availability Zones
- Internet Gateway + NAT Gateway (with Elastic IP)
- Route tables correctly associated
- Least-privilege security groups
- **Idempotent** — safe to run multiple times
- Automatic resource tagging
- boto3 **waiters** so the script waits for resources to become ready
- Ordered teardown (instances → NAT Gateways → IGW → route tables → subnets → security groups → VPC)

## Structure
aws-vpc-automation/
├── boto3/
│   ├── create_vpc.py
│   └── destroy_vpc.py
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── README.md


## Design Principles
- Nothing is done manually in the AWS console
- Creation and deletion order is enforced in code to avoid dependency errors
- Every resource is tagged
- Scripts are written to be readable and repeatable by other engineers

## Status
Active development. Core automation patterns (idempotency, waiters, ordered teardown, least-privilege) are implemented and documented for interview and production use.

## Related
This project supports real-world infrastructure work and is referenced in my professional materials for Linux Admin / AWS / DevOps roles.
