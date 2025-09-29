import boto3
from botocore.exceptions import ClientError

class ALBService:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.elbv2 = self.session.client('elbv2')
        self.ec2 = self.session.client('ec2')
        self.region = region
    
    def create_alb(self, infra_name, vpc_id, subnets, security_group_id):
        try:
            print(f"Creating ALB with initial subnets: {subnets}")
            
            # If no subnets provided, get all public subnets from VPC
            if not subnets:
                subnets = self._get_all_public_subnets(vpc_id)
                print(f"Retrieved public subnets: {subnets}")
            
            if not subnets:
                raise Exception(f"No public subnets found in VPC {vpc_id}. ALB requires public subnets.")
            
            # Get subnets in different AZs
            unique_az_subnets = self._get_subnets_in_different_azs(subnets)
            
            print(f"Using subnets in different AZs: {unique_az_subnets}")
            
            # If we don't have enough subnets in different AZs, use what we have
            if len(unique_az_subnets) < 2:
                print(f"Warning: Only {len(unique_az_subnets)} subnets in different AZs available")
                if len(unique_az_subnets) == 0 and len(subnets) > 0:
                    # Use the first subnet if that's all we have
                    unique_az_subnets = [subnets[0]]
                elif len(unique_az_subnets) == 1:
                    # Use the single subnet we found
                    pass
                else:
                    raise Exception(f"ALB requires at least 1 subnet. Found {len(unique_az_subnets)} subnets.")
            
            # Create Target Group
            tg_response = self.elbv2.create_target_group(
                Name=f"{infra_name}-tg",
                Protocol='HTTP',
                Port=80,
                VpcId=vpc_id,
                HealthCheckProtocol='HTTP',
                HealthCheckPort='80',
                HealthCheckPath='/',
                HealthCheckIntervalSeconds=30,
                HealthCheckTimeoutSeconds=5,
                HealthyThresholdCount=2,
                UnhealthyThresholdCount=2,
                TargetType='ip',
                Matcher={'HttpCode': '200'},
                Tags=[
                    {'Key': 'Name', 'Value': f'{infra_name}-tg'},
                    {'Key': 'Infra', 'Value': infra_name}
                ]
            )
            target_group_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
            print(f"Created Target Group: {target_group_arn}")
            
            # Create Load Balancer (internet-facing in public subnets)
            alb_response = self.elbv2.create_load_balancer(
                Name=f"{infra_name}-alb",
                Subnets=unique_az_subnets,
                SecurityGroups=[security_group_id] if security_group_id else [],
                Scheme='internet-facing',  # Internet-facing ALB
                Tags=[
                    {'Key': 'Name', 'Value': f'{infra_name}-alb'},
                    {'Key': 'Infra', 'Value': infra_name}
                ],
                Type='application',
                IpAddressType='ipv4'
            )
            alb_arn = alb_response['LoadBalancers'][0]['LoadBalancerArn']
            alb_dns = alb_response['LoadBalancers'][0]['DNSName']
            
            print(f"Creating ALB: {alb_arn}")
            print(f"ALB DNS: {alb_dns}")
            print(f"ALB Subnets: {unique_az_subnets}")
            
            # Wait for ALB to be active
            waiter = self.elbv2.get_waiter('load_balancer_available')
            waiter.wait(LoadBalancerArns=[alb_arn])
            print("ALB is now active")
            
            # Create HTTP listener
            listener_response = self.elbv2.create_listener(
                LoadBalancerArn=alb_arn,
                Protocol='HTTP',
                Port=80,
                DefaultActions=[{
                    'Type': 'forward',
                    'TargetGroupArn': target_group_arn
                }]
            )
            print(f"Created listener: {listener_response['Listeners'][0]['ListenerArn']}")
            
            return alb_arn, target_group_arn
            
        except ClientError as e:
            print(f"ALB creation error: {str(e)}")
            raise Exception(f"ALB creation failed: {str(e)}")
    
    def _get_subnets_in_different_azs(self, subnets):
        """Get one subnet per Availability Zone to avoid AZ conflicts"""
        if not subnets:
            return []
        
        try:
            # Get subnet details to check their AZs
            response = self.ec2.describe_subnets(SubnetIds=subnets)
            subnet_details = response['Subnets']
            
            # Group subnets by AZ and pick one from each AZ
            az_subnets = {}
            for subnet in subnet_details:
                az = subnet['AvailabilityZone']
                if az not in az_subnets:
                    az_subnets[az] = subnet['SubnetId']
            
            # Return one subnet from each AZ
            unique_subnets = list(az_subnets.values())
            print(f"Subnets in different AZs: {unique_subnets}")
            
            return unique_subnets
            
        except ClientError as e:
            print(f"Error getting subnet AZ information: {str(e)}")
            # If we can't get AZ info, just return the original subnets
            return subnets
    
    def _get_all_public_subnets(self, vpc_id):
        """Get all public subnets from the VPC by checking route tables for Internet Gateway"""
        try:
            # First try to get subnets with public IP mapping enabled
            response = self.ec2.describe_subnets(Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'map-public-ip-on-launch', 'Values': ['true']}
            ])
            
            subnets = [subnet['SubnetId'] for subnet in response['Subnets']]
            
            # If no subnets found with public IP mapping, try to find public subnets by route table
            if not subnets:
                subnets = self._find_public_subnets_by_route_table(vpc_id)
            
            print(f"All public subnets in VPC: {subnets}")
            return subnets
            
        except ClientError as e:
            print(f"Error getting all public subnets: {str(e)}")
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
    
    def get_alb_dns_name(self, alb_arn):
        try:
            response = self.elbv2.describe_load_balancers(
                LoadBalancerArns=[alb_arn]
            )
            dns_name = response['LoadBalancers'][0]['DNSName']
            print(f"ALB DNS Name: {dns_name}")
            return dns_name
        except ClientError as e:
            raise Exception(f"Failed to get ALB DNS name: {str(e)}")
    
    def get_alb_dns(self, infra_name):
        """Get ALB DNS name by ALB name (added missing method)"""
        try:
            alb_name = f"{infra_name}-alb"
            response = self.elbv2.describe_load_balancers(Names=[alb_name])
            if response['LoadBalancers']:
                dns_name = response['LoadBalancers'][0]['DNSName']
                print(f"✅ ALB DNS retrieved: {dns_name}")
                return dns_name
            return "alb-dns-not-available"
        except ClientError as e:
            print(f"❌ Error getting ALB DNS: {str(e)}")
            return "alb-dns-not-available"