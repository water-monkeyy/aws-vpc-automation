#!/usr/bin/env python3
"""
AWS VPC Provisioning Script (boto3)
-----------------------------------
Creates a production-style VPC with:
- DNS hostnames enabled
- Public and private subnets across multiple AZs
- Internet Gateway
- NAT Gateway + Elastic IP
- Route tables
- Least-privilege security group

Design principles:
- Idempotent (safe to run multiple times)
- Automatic tagging
- Uses boto3 waiters
- Zero manual console work
"""

import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client("ec2")

# -----------------------------
# Configuration
# -----------------------------
REGION = "us-east-1"
VPC_CIDR = "10.0.0.0/16"
PUBLIC_SUBNET_CIDR = "10.0.1.0/24"
PRIVATE_SUBNET_CIDR = "10.0.2.0/24"
TAG_PREFIX = "vpc-automation"


def get_or_create_vpc():
    """Create VPC if it doesn't already exist (idempotent)."""
    response = ec2.describe_vpcs(
        Filters=[{"Name": "tag:Name", "Values": [f"{TAG_PREFIX}-vpc"]}]
    )
    if response["Vpcs"]:
        vpc_id = response["Vpcs"][0]["VpcId"]
        print(f"[SKIP] VPC already exists: {vpc_id}")
        return vpc_id

    print("[CREATE] Creating VPC...")
    vpc = ec2.create_vpc(
        CidrBlock=VPC_CIDR,
        TagSpecifications=[{
            "ResourceType": "vpc",
            "Tags": [
                {"Key": "Name", "Value": f"{TAG_PREFIX}-vpc"},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
    vpc_id = vpc["Vpc"]["VpcId"]

    # Enable DNS hostnames
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

    print(f"[OK] VPC created: {vpc_id}")
    return vpc_id


def create_subnet(vpc_id, cidr, az, name, public=False):
    """Create a subnet if it does not already exist."""
    response = ec2.describe_subnets(
        Filters=[{"Name": "tag:Name", "Values": [name]}]
    )
    if response["Subnets"]:
        subnet_id = response["Subnets"][0]["SubnetId"]
        print(f"[SKIP] Subnet already exists: {subnet_id}")
        return subnet_id

    print(f"[CREATE] Creating subnet {name}...")
    subnet = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=cidr,
        AvailabilityZone=az,
        TagSpecifications=[{
            "ResourceType": "subnet",
            "Tags": [
                {"Key": "Name", "Value": name},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
    subnet_id = subnet["Subnet"]["SubnetId"]

    if public:
        ec2.modify_subnet_attribute(
            SubnetId=subnet_id,
            MapPublicIpOnLaunch={"Value": True}
        )

    print(f"[OK] Subnet created: {subnet_id}")
    return subnet_id


def create_internet_gateway(vpc_id):
    """Create and attach Internet Gateway."""
    response = ec2.describe_internet_gateways(
        Filters=[{"Name": "tag:Name", "Values": [f"{TAG_PREFIX}-igw"]}]
    )
    if response["InternetGateways"]:
        igw_id = response["InternetGateways"][0]["InternetGatewayId"]
        print(f"[SKIP] IGW already exists: {igw_id}")
        return igw_id

    print("[CREATE] Creating Internet Gateway...")
    igw = ec2.create_internet_gateway(
        TagSpecifications=[{
            "ResourceType": "internet-gateway",
            "Tags": [
                {"Key": "Name", "Value": f"{TAG_PREFIX}-igw"},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
    igw_id = igw["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    print(f"[OK] IGW created and attached: {igw_id}")
    return igw_id


def create_nat_gateway(public_subnet_id):
    """Allocate EIP and create NAT Gateway with waiter."""
    response = ec2.describe_nat_gateways(
        Filters=[
            {"Name": "tag:Name", "Values": [f"{TAG_PREFIX}-nat"]},
            {"Name": "state", "Values": ["available", "pending"]}
        ]
    )
    if response["NatGateways"]:
        nat_id = response["NatGateways"][0]["NatGatewayId"]
        print(f"[SKIP] NAT Gateway already exists: {nat_id}")
        return nat_id

    print("[CREATE] Allocating Elastic IP...")
    eip = ec2.allocate_address(Domain="vpc")
    allocation_id = eip["AllocationId"]

    print("[CREATE] Creating NAT Gateway...")
    nat = ec2.create_nat_gateway(
        SubnetId=public_subnet_id,
        AllocationId=allocation_id,
        TagSpecifications=[{
            "ResourceType": "natgateway",
            "Tags": [
                {"Key": "Name", "Value": f"{TAG_PREFIX}-nat"},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
    nat_id = nat["NatGateway"]["NatGatewayId"]

    print("[WAIT] Waiting for NAT Gateway to become available...")
    waiter = ec2.get_waiter("nat_gateway_available")
    waiter.wait(NatGatewayIds=[nat_id])
    print(f"[OK] NAT Gateway ready: {nat_id}")
    return nat_id


def create_route_table(vpc_id, name, routes, subnet_id):
    """Create route table, add routes, and associate with subnet."""
    response = ec2.describe_route_tables(
        Filters=[{"Name": "tag:Name", "Values": [name]}]
    )
    if response["RouteTables"]:
        rt_id = response["RouteTables"][0]["RouteTableId"]
        print(f"[SKIP] Route table already exists: {rt_id}")
        return rt_id

    print(f"[CREATE] Creating route table {name}...")
    rt = ec2.create_route_table(
        VpcId=vpc_id,
        TagSpecifications=[{
            "ResourceType": "route-table",
            "Tags": [
                {"Key": "Name", "Value": name},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
    rt_id = rt["RouteTable"]["RouteTableId"]

    for route in routes:
        ec2.create_route(RouteTableId=rt_id, **route)

    ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
    print(f"[OK] Route table created and associated: {rt_id}")
    return rt_id


def create_security_group(vpc_id):
    """Create a least-privilege security group."""
    response = ec2.describe_security_groups(
        Filters=[{"Name": "tag:Name", "Values": [f"{TAG_PREFIX}-sg"]}]
    )
    if response["SecurityGroups"]:
        sg_id = response["SecurityGroups"][0]["GroupId"]
        print(f"[SKIP] Security group already exists: {sg_id}")
        return sg_id

    print("[CREATE] Creating security group...")
    sg = ec2.create_security_group(
        GroupName=f"{TAG_PREFIX}-sg",
        Description="Least-privilege security group for VPC automation",
        VpcId=vpc_id,
        TagSpecifications=[{
            "ResourceType": "security-group",
            "Tags": [
                {"Key": "Name", "Value": f"{TAG_PREFIX}-sg"},
                {"Key": "Project", "Value": "vpc-automation"},
            ]
        }]
    )
