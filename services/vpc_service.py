import boto3
from botocore.exceptions import ClientError
import time

class VPCService:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.ec2 = self.session.client('ec2')
        self.region = region
    
    def list_vpcs(self):
        try:
            response = self.ec2.describe_vpcs()
            vpcs = []
            for vpc in response['Vpcs']:
                vpc_info = {
                    'VpcId': vpc['VpcId'],
                    'CidrBlock': vpc['CidrBlock'],
                    'IsDefault': vpc.get('IsDefault', False)
                }
                # Get VPC name from tags
                vpc_name = 'Unnamed'
                for tag in vpc.get('Tags', []):
                    if tag['Key'] == 'Name':
                        vpc_name = tag['Value']
                        break
                vpc_info['Name'] = vpc_name
                
                vpcs.append(vpc_info)
            return vpcs
        except ClientError as e:
            print(f"Error listing VPCs: {str(e)}")
            return {'error': str(e)}
    
    def create_vpc(self, infra_name, vpc_name, public_subnets_count, private_subnets_count):
        try:
            # Ensure minimum 2 public subnets for ALB
            public_subnets_count = max(2, public_subnets_count)
            private_subnets_count = max(2, private_subnets_count)  # Ensure at least 2 private subnets
            
            print(f"🚀 Creating VPC: {vpc_name}")
            
            # Create VPC
            vpc_response = self.ec2.create_vpc(
                CidrBlock='10.0.0.0/16',
                TagSpecifications=[{
                    'ResourceType': 'vpc',
                    'Tags': [
                        {'Key': 'Name', 'Value': vpc_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            vpc_id = vpc_response['Vpc']['VpcId']
            
            # Wait for VPC to be available
            waiter = self.ec2.get_waiter('vpc_available')
            waiter.wait(VpcIds=[vpc_id])
            
            # Enable DNS hostnames and DNS support
            self.ec2.modify_vpc_attribute(
                VpcId=vpc_id,
                EnableDnsHostnames={'Value': True}
            )
            self.ec2.modify_vpc_attribute(
                VpcId=vpc_id,
                EnableDnsSupport={'Value': True}
            )
            
            # Create Internet Gateway
            igw_response = self.ec2.create_internet_gateway(
                TagSpecifications=[{
                    'ResourceType': 'internet-gateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-igw'},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            igw_id = igw_response['InternetGateway']['InternetGatewayId']
            
            # Attach IGW to VPC
            self.ec2.attach_internet_gateway(
                InternetGatewayId=igw_id,
                VpcId=vpc_id
            )
            
            # Get available AZs for the region
            az_response = self.ec2.describe_availability_zones(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )
            available_azs = [az['ZoneName'] for az in az_response['AvailabilityZones']]
            
            # Create public and private subnets with exact CIDR blocks as in your example
            public_subnets = self._create_subnets(vpc_id, infra_name, 'public', 
                                                public_subnets_count, 
                                                '10.0.0.0/20', available_azs)
            private_subnets = self._create_subnets(vpc_id, infra_name, 'private',
                                                 private_subnets_count,
                                                 '10.0.128.0/20', available_azs)
            
            # Create NAT Gateway in first public subnet
            nat_gateway_id, eip_allocation_id = self._create_nat_gateway(public_subnets[0], infra_name)
            
            # Create route tables
            public_rt_id = self._create_public_route_table(vpc_id, igw_id, infra_name)
            private_rt_ids = self._create_private_route_tables(vpc_id, infra_name, nat_gateway_id, private_subnets, available_azs)
            
            # Associate subnets with route tables
            for i, subnet in enumerate(public_subnets):
                self.ec2.associate_route_table(
                    RouteTableId=public_rt_id,
                    SubnetId=subnet
                )
            
            # Associate private subnets with their respective route tables
            for i, subnet in enumerate(private_subnets):
                rt_id = private_rt_ids[i % len(private_rt_ids)]
                self.ec2.associate_route_table(
                    RouteTableId=rt_id,
                    SubnetId=subnet
                )
            
            # Create S3 VPC Endpoint
            self._create_s3_endpoint(vpc_id, private_rt_ids, infra_name)
            
            print(f"✅ VPC created: {vpc_id}")
            print(f"✅ Public subnets: {public_subnets}")
            print(f"✅ Private subnets: {private_subnets}")
            print(f"✅ NAT Gateway created: {nat_gateway_id}")
            
            # Return the values properly
            return vpc_id, public_subnets, private_subnets
            
        except ClientError as e:
            raise Exception(f"❌ VPC creation failed: {str(e)}")
    
    def _create_subnets(self, vpc_id, infra_name, subnet_type, count, base_cidr, available_azs):
        subnets = []
        for i in range(count):
            az = available_azs[i % len(available_azs)]
            
            # Calculate CIDR block exactly like your example
            if subnet_type == 'public':
                # Public subnets: 10.0.0.0/20, 10.0.16.0/20, etc.
                third_octet = i * 16
                subnet_cidr = f'10.0.{third_octet}.0/20'
            else:
                # Private subnets: 10.0.128.0/20, 10.0.144.0/20, etc.
                third_octet = 128 + (i * 16)
                subnet_cidr = f'10.0.{third_octet}.0/20'
            
            response = self.ec2.create_subnet(
                VpcId=vpc_id,
                CidrBlock=subnet_cidr,
                AvailabilityZone=az,
                TagSpecifications=[{
                    'ResourceType': 'subnet',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-subnet-{subnet_type}{i+1}-{az.split("-")[-1]}'},  # FIXED: Use infra_name instead of vpc_name
                        {'Key': 'Infra', 'Value': infra_name},
                        {'Key': 'Type', 'Value': subnet_type}
                    ]
                }]
            )
            subnet_id = response['Subnet']['SubnetId']
            subnets.append(subnet_id)
            
            if subnet_type == 'public':
                self.ec2.modify_subnet_attribute(
                    SubnetId=subnet_id,
                    MapPublicIpOnLaunch={'Value': True}
                )
        
        return subnets
    
    def _create_nat_gateway(self, public_subnet_id, infra_name):
        """Create NAT Gateway in public subnet"""
        try:
            # Allocate Elastic IP
            eip_response = self.ec2.allocate_address(
                Domain='vpc',
                TagSpecifications=[{
                    'ResourceType': 'elastic-ip',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-nat-eip'},  # FIXED: Use infra_name instead of vpc_name
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            eip_allocation_id = eip_response['AllocationId']
            
            # Create NAT Gateway
            nat_response = self.ec2.create_nat_gateway(
                SubnetId=public_subnet_id,
                AllocationId=eip_allocation_id,
                TagSpecifications=[{
                    'ResourceType': 'natgateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-nat-{public_subnet_id.split("-")[1]}'},  # FIXED: Use infra_name instead of vpc_name
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
            
            # Wait for NAT Gateway to be available
            print("⏳ Waiting for NAT Gateway to become available...")
            waiter = self.ec2.get_waiter('nat_gateway_available')
            waiter.wait(NatGatewayIds=[nat_gateway_id])
            
            print(f"✅ NAT Gateway created: {nat_gateway_id}")
            return nat_gateway_id, eip_allocation_id
            
        except ClientError as e:
            raise Exception(f"NAT Gateway creation failed: {str(e)}")
    
    def _create_public_route_table(self, vpc_id, igw_id, infra_name):
        rt_response = self.ec2.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[{
                'ResourceType': 'route-table',
                'Tags': [
                    {'Key': 'Name', 'Value': f'{infra_name}-rtb-public'},  # FIXED: Use infra_name instead of vpc_name
                    {'Key': 'Infra', 'Value': infra_name}
                ]
            }]
        )
        rt_id = rt_response['RouteTable']['RouteTableId']
        
        # Add route to internet gateway
        self.ec2.create_route(
            RouteTableId=rt_id,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw_id
        )
        
        return rt_id
    
    def _create_private_route_tables(self, vpc_id, infra_name, nat_gateway_id, private_subnets, available_azs):
        """Create private route tables with NAT Gateway routing"""
        private_rt_ids = []
        
        # Create one route table per AZ for private subnets
        for i in range(len(private_subnets)):
            az_suffix = available_azs[i % len(available_azs)].split('-')[-1]
            rt_response = self.ec2.create_route_table(
                VpcId=vpc_id,
                TagSpecifications=[{
                    'ResourceType': 'route-table',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-rtb-private{i+1}-{az_suffix}'},  # FIXED: Use infra_name instead of vpc_name
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            rt_id = rt_response['RouteTable']['RouteTableId']
            
            # Add route to NAT Gateway
            self.ec2.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock='0.0.0.0/0',
                NatGatewayId=nat_gateway_id
            )
            
            private_rt_ids.append(rt_id)
        
        return private_rt_ids
    
    def _create_s3_endpoint(self, vpc_id, private_rt_ids, infra_name):
        """Create S3 VPC Gateway Endpoint"""
        try:
            endpoint_response = self.ec2.create_vpc_endpoint(
                VpcId=vpc_id,
                ServiceName=f'com.amazonaws.{self.region}.s3',
                RouteTableIds=private_rt_ids,
                VpcEndpointType='Gateway',
                TagSpecifications=[{
                    'ResourceType': 'vpc-endpoint',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'{infra_name}-vpce-s3'},  # FIXED: Use infra_name instead of vpc_name
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            print(f"✅ S3 VPC Endpoint created: {endpoint_response['VpcEndpoint']['VpcEndpointId']}")
            return endpoint_response['VpcEndpoint']['VpcEndpointId']
        except ClientError as e:
            print(f"⚠️  S3 Endpoint creation failed: {str(e)}")
            return None
    
    def get_public_subnets(self, vpc_id):
        try:
            # First try by public IP mapping
            response = self.ec2.describe_subnets(Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'map-public-ip-on-launch', 'Values': ['true']}
            ])
            
            if response['Subnets']:
                return [subnet['SubnetId'] for subnet in response['Subnets']]
            
            # Fallback: try by route table with Internet Gateway
            return self._find_public_subnets_by_route_table(vpc_id)
            
        except ClientError as e:
            print(f"Error getting public subnets: {str(e)}")
            return []

    def _find_public_subnets_by_route_table(self, vpc_id):
        """Find public subnets by checking route tables for Internet Gateway"""
        try:
            # Get all subnets in the VPC
            all_subnets = self.ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            public_subnets = []
            
            for subnet in all_subnets['Subnets']:
                subnet_id = subnet['SubnetId']
                
                # Check route tables associated with this subnet
                route_tables = self.ec2.describe_route_tables(
                    Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
                )
                
                # If no specific route table, check main route table
                if not route_tables['RouteTables']:
                    route_tables = self.ec2.describe_route_tables(
                        Filters=[
                            {'Name': 'vpc-id', 'Values': [vpc_id]},
                            {'Name': 'association.main', 'Values': ['true']}
                        ]
                    )
                
                # Check if any route table has an Internet Gateway route
                for route_table in route_tables['RouteTables']:
                    for route in route_table['Routes']:
                        if 'GatewayId' in route and route['GatewayId'].startswith('igw-'):
                            if subnet_id not in public_subnets:
                                public_subnets.append(subnet_id)
                            break
            
            return public_subnets
            
        except ClientError as e:
            print(f"Error finding public subnets by route table: {str(e)}")
            return []
    
    def get_private_subnets(self, vpc_id):
        """Get private subnets - all subnets that are not public"""
        try:
            # Get all subnets in the VPC
            all_subnets = self.ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            # Get public subnets first
            public_subnets = self.get_public_subnets(vpc_id)
            all_subnet_ids = [subnet['SubnetId'] for subnet in all_subnets['Subnets']]
            
            # Private subnets are all subnets that are not public
            private_subnets = [subnet_id for subnet_id in all_subnet_ids if subnet_id not in public_subnets]
            
            print(f"Found {len(private_subnets)} private subnets: {private_subnets}")
            return private_subnets
            
        except ClientError as e:
            print(f"Error getting private subnets: {str(e)}")
            return []