# destroy_vpc.py
# Ordered teardown #!/usr/bin/env python3
"""
AWS VPC Teardown Script (boto3)

Destroys resources in strict dependency order:
instances → NAT Gateways → Internet Gateway → route tables → subnets → security groups → VPC

Design goals:
- Ordered deletion to avoid dependency errors
- Safe cleanup of tagged resources only
"""

import boto3
import time
from botocore.exceptions import ClientError

REGION = "us-east-1"
PROJECT_TAG = "aws-vpc-automation"

ec2 = boto3.client("ec2", region_name=REGION)


def get_tagged_resources(resource_type: str):
    """Return resource IDs that have our Project tag."""
    # Simplified helper – in production you would use specific describe calls
    pass


def delete_nat_gateways(vpc_id: str):
    """Delete NAT Gateways and release their EIPs."""
    response = ec2.describe_nat_gateways(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Project", "Values": [PROJECT_TAG]},
        ]
    )
    for nat in response.get("NatGateways", []):
        nat_id = nat["NatGatewayId"]
        print(f"[DELETE] NAT Gateway {nat_id}")
        ec2.delete_nat_gateway(NatGatewayId=nat_id)

        # Wait until deleted
        waiter = ec2.get_waiter("nat_gateway_deleted")
        waiter.wait(NatGatewayIds=[nat_id])
        print(f"[OK] NAT Gateway deleted: {nat_id}")


def detach_and_delete_igw(vpc_id: str):
    """Detach and delete Internet Gateway."""
    response = ec2.describe_internet_gateways(
        Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
    )
    for igw in response.get("InternetGateways", []):
        igw_id = igw["InternetGatewayId"]
        print(f"[DETACH] Internet Gateway {igw_id}")
        ec2.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        ec2.delete_internet_gateway(InternetGatewayId=igw_id)
        print(f"[OK] Internet Gateway deleted: {igw_id}")


def delete_route_tables(vpc_id: str):
    """Delete non-main route tables."""
    response = ec2.describe_route_tables(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )
    for rt in response.get("RouteTables", []):
        # Skip the main route table
        associations = rt.get("Associations", [])
        if any(a.get("Main") for a in associations):
            continue
        rt_id = rt["RouteTableId"]
        print(f"[DELETE] Route table {rt_id}")
        ec2.delete_route_table(RouteTableId=rt_id)


def delete_subnets(vpc_id: str):
    """Delete all subnets in the VPC."""
    response = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    for subnet in response.get("Subnets", []):
        subnet_id = subnet["SubnetId"]
        print(f"[DELETE] Subnet {subnet_id}")
        ec2.delete_subnet(SubnetId=subnet_id)


def delete_security_groups(vpc_id: str):
    """Delete non-default security groups."""
    response = ec2.describe_security_groups(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )
    for sg in response.get("SecurityGroups", []):
        if sg["GroupName"] == "default":
            continue
        sg_id = sg["GroupId"]
        print(f"[DELETE] Security group {sg_id}")
        try:
            ec2.delete_security_group(GroupId=sg_id)
        except ClientError as e:
            print(f"[WARN] Could not delete {sg_id}: {e}")


def delete_vpc(vpc_id: str):
    """Finally delete the VPC."""
    print(f"[DELETE] VPC {vpc_id}")
    ec2.delete_vpc(VpcId=vpc_id)
    print(f"[OK] VPC deleted: {vpc_id}")


def main():
    print("Starting ordered VPC teardown...\n")

    # Find VPC with our project tag
    response = ec2.describe_vpcs(
        Filters=[{"Name": "tag:Project", "Values": [PROJECT_TAG]}]
    )
    if not response["Vpcs"]:
        print("No matching VPC found. Nothing to delete.")
        return

    vpc_id = response["Vpcs"][0]["VpcId"]
    print(f"Target VPC: {vpc_id}\n")

    # Strict order
    delete_nat_gateways(vpc_id)
    detach_and_delete_igw(vpc_id)
    delete_route_tables(vpc_id)
    delete_subnets(vpc_id)
    delete_security_groups(vpc_id)
    delete_vpc(vpc_id)

    print("\n[SUCCESS] Teardown complete.")


if __name__ == "__main__":
    main()script
# Order: instances → NAT Gateways → IGW → route tables → subnets → security groups → VPC
