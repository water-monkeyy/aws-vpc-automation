# create_vpc.py
# AWS VPC provisioning script using boto3
# - Idempotent
# - Uses waiters
# - Applies tags
# - Creates VPC, subnets, IGW, NAT Gateway, route tables, security groups
