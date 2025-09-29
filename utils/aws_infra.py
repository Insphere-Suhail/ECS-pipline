import boto3
import json
import time
import subprocess
import git
import docker
from botocore.exceptions import ClientError, NoCredentialsError

class AWSInfraCreator:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.region = region
        
    def validate_credentials(self):
        """Validate AWS credentials and get account info"""
        try:
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            
            # Check basic permissions
            ec2 = self.session.client('ec2')
            ec2.describe_vpcs(MaxResults=5)
            
            return {
                'success': True,
                'account_id': identity['Account'],
                'user_arn': identity['Arn']
            }
        except (ClientError, NoCredentialsError) as e:
            return {'success': False, 'error': str(e)}
    
    def get_existing_resources(self):
        """Fetch existing AWS resources"""
        resources = {}
        
        # Get VPCs
        ec2 = self.session.client('ec2')
        vpcs = ec2.describe_vpcs()
        resources['vpcs'] = [
            {'id': vpc['VpcId'], 'name': next((tag['Value'] for tag in vpc.get('Tags', []) if tag['Key'] == 'Name'), vpc['VpcId'])}
            for vpc in vpcs['Vpcs']
        ]
        
        # Get Security Groups
        sgs = ec2.describe_security_groups()
        resources['security_groups'] = [
            {'id': sg['GroupId'], 'name': sg['GroupName']}
            for sg in sgs['SecurityGroups']
        ]
        
        # Get Key Pairs
        keys = ec2.describe_key_pairs()
        resources['key_pairs'] = [kp['KeyName'] for kp in keys['KeyPairs']]
        
        return resources
    
    def create_vpc(self, vpc_name, cidr_block, public_subnets, private_subnets):
        """Create VPC with subnets, IGW, route tables"""
        ec2 = self.session.client('ec2')
        
        # Create VPC
        vpc_response = ec2.create_vpc(CidrBlock=cidr_block)
        vpc_id = vpc_response['Vpc']['VpcId']
        
        # Add Name tag
        ec2.create_tags(Resources=[vpc_id], Tags=[{'Key': 'Name', 'Value': vpc_name}])
        
        # Enable DNS hostnames
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        
        # Create Internet Gateway
        igw_response = ec2.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        
        # Create Public Subnets
        public_subnet_ids = []
        azs = ['a', 'b']  # Use 2 AZs
        for i in range(public_subnets):
            subnet_cidr = f"10.0.{i}.0/24"
            subnet_response = ec2.create_subnet(
                VpcId=vpc_id, CidrBlock=subnet_cidr,
                AvailabilityZone=f"{self.region}{azs[i % 2]}"
            )
            public_subnet_ids.append(subnet_response['Subnet']['SubnetId'])
        
        # Create Private Subnets
        private_subnet_ids = []
        for i in range(private_subnets):
            subnet_cidr = f"10.0.{i + 10}.0/24"
            subnet_response = ec2.create_subnet(
                VpcId=vpc_id, CidrBlock=subnet_cidr,
                AvailabilityZone=f"{self.region}{azs[i % 2]}"
            )
            private_subnet_ids.append(subnet_response['Subnet']['SubnetId'])
        
        # Create Route Tables
        public_rt = ec2.create_route_table(VpcId=vpc_id)
        public_rt_id = public_rt['RouteTable']['RouteTableId']
        
        # Add route to IGW for public subnets
        ec2.create_route(
            RouteTableId=public_rt_id,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw_id
        )
        
        # Associate public subnets with public route table
        for subnet_id in public_subnet_ids:
            ec2.associate_route_table(
                RouteTableId=public_rt_id,
                SubnetId=subnet_id
            )
        
        return {
            'vpc_id': vpc_id,
            'public_subnet_ids': public_subnet_ids,
            'private_subnet_ids': private_subnet_ids,
            'igw_id': igw_id
        }
    
    def create_security_groups(self, vpc_id, app_name, create_server_sg=True, create_alb_sg=True, 
                             create_rds_sg=True, create_vpn_sg=True):
        """Create security groups based on selected options"""
        ec2 = self.session.client('ec2')
        sgs = {}
        
        if create_alb_sg:
            # ALB Security Group
            alb_sg = ec2.create_security_group(
                GroupName=f"{app_name}-alb-sg",
                Description=f"ALB security group for {app_name}",
                VpcId=vpc_id
            )
            alb_sg_id = alb_sg['GroupId']
            
            # ALB inbound rules
            ec2.authorize_security_group_ingress(
                GroupId=alb_sg_id,
                IpPermissions=[
                    {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                    {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
                ]
            )
            sgs['alb'] = alb_sg_id
        
        if create_vpn_sg:
            # VPN Security Group
            vpn_sg = ec2.create_security_group(
                GroupName=f"{app_name}-vpn-sg",
                Description=f"VPN security group for {app_name}",
                VpcId=vpc_id
            )
            vpn_sg_id = vpn_sg['GroupId']
            
            # VPN inbound rules
            ec2.authorize_security_group_ingress(
                GroupId=vpn_sg_id,
                IpPermissions=[
                    {'IpProtocol': 'tcp', 'FromPort': 10086, 'ToPort': 10086, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                    {'IpProtocol': 'udp', 'FromPort': 51820, 'ToPort': 51820, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
                ]
            )
            sgs['vpn'] = vpn_sg_id
        
        if create_server_sg:
            # Server Security Group
            server_sg = ec2.create_security_group(
                GroupName=f"{app_name}-server-sg",
                Description=f"Server security group for {app_name}",
                VpcId=vpc_id
            )
            server_sg_id = server_sg['GroupId']
            sgs['server'] = server_sg_id
            
            # Server inbound rules (will be updated after other SGs are created)
            if 'vpn' in sgs and 'alb' in sgs:
                ec2.authorize_security_group_ingress(
                    GroupId=server_sg_id,
                    IpPermissions=[
                        {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'UserIdGroupPairs': [{'GroupId': sgs['vpn']}]},
                        {'IpProtocol': 'tcp', 'FromPort': 80, 'ToPort': 80, 'UserIdGroupPairs': [{'GroupId': sgs['alb']}]},
                        {'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443, 'UserIdGroupPairs': [{'GroupId': sgs['alb']}]}
                    ]
                )
        
        if create_rds_sg:
            # RDS Security Group
            rds_sg = ec2.create_security_group(
                GroupName=f"{app_name}-rds-sg",
                Description=f"RDS security group for {app_name}",
                VpcId=vpc_id
            )
            rds_sg_id = rds_sg['GroupId']
            sgs['rds'] = rds_sg_id
            
            # RDS inbound rules
            if 'server' in sgs and 'vpn' in sgs:
                ec2.authorize_security_group_ingress(
                    GroupId=rds_sg_id,
                    IpPermissions=[
                        {'IpProtocol': 'tcp', 'FromPort': 3306, 'ToPort': 3306, 
                         'UserIdGroupPairs': [{'GroupId': sgs['server']}, {'GroupId': sgs['vpn']}]}
                    ]
                )
        
        return sgs
    
    def create_alb(self, alb_name, vpc_id, subnet_ids, security_group_ids):
        """Create Application Load Balancer"""
        elbv2 = self.session.client('elbv2')
        
        # Create ALB
        alb_response = elbv2.create_load_balancer(
            Name=alb_name,
            Subnets=subnet_ids,
            SecurityGroups=security_group_ids,
            Scheme='internet-facing',
            Type='application'
        )
        alb_arn = alb_response['LoadBalancers'][0]['LoadBalancerArn']
        alb_dns = alb_response['LoadBalancers'][0]['DNSName']
        
        # Create Target Group
        tg_response = elbv2.create_target_group(
            Name=f"{alb_name}-tg",
            Protocol='HTTP',
            Port=80,
            VpcId=vpc_id,
            TargetType='ip',
            HealthCheckPath='/',
            HealthCheckProtocol='HTTP'
        )
        tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
        
        # Create Listeners
        elbv2.create_listener(
            LoadBalancerArn=alb_arn,
            Protocol='HTTP',
            Port=80,
            DefaultActions=[{'Type': 'forward', 'TargetGroupArn': tg_arn}]
        )
        
        return {'alb_arn': alb_arn, 'alb_dns': alb_dns, 'tg_arn': tg_arn}
    
    def create_ecr_repo(self, repo_name):
        """Create ECR repository and push sample image"""
        ecr = self.session.client('ecr')
        
        # Create repository
        ecr.create_repository(repositoryName=repo_name)
        repo_uri = f"{self.session.client('sts').get_caller_identity()['Account']}.dkr.ecr.{self.region}.amazonaws.com/{repo_name}"
        
        # Clone and build sample image
        try:
            # Clone sample repo
            repo_url = "https://github.com/Insphere-Suhail/ECS-ARM-Image.git"
            local_path = f"/tmp/{repo_name}"
            
            if os.path.exists(local_path):
                shutil.rmtree(local_path)
            
            git.Repo.clone_from(repo_url, local_path)
            
            # Build and push Docker image
            client = docker.from_env()
            image, build_logs = client.images.build(
                path=local_path,
                tag=f"{repo_uri}:latest",
                platform="linux/arm64"
            )
            
            # Get ECR login token
            auth_token = ecr.get_authorization_token()
            username, password = base64.b64decode(auth_token['authorizationData'][0]['authorizationToken']).decode().split(':')
            registry = auth_token['authorizationData'][0]['proxyEndpoint']
            
            client.login(username=username, password=password, registry=registry)
            client.images.push(f"{repo_uri}:latest")
            
        except Exception as e:
            print(f"Image push failed: {e}")
            # Return repo URI even if push fails
            return repo_uri
        
        return repo_uri
    
    def create_iam_roles(self, app_name):
        """Create IAM roles for ECS"""
        iam = self.session.client('iam')
        
        # Task Execution Role
        try:
            task_exec_role = iam.create_role(
                RoleName='ecsTaskExecutionRole',
                AssumeRolePolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }]
                })
            )
            iam.attach_role_policy(
                RoleName='ecsTaskExecutionRole',
                PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
            )
            iam.attach_role_policy(
                RoleName='ecsTaskExecutionRole',
                PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess'
            )
        except iam.exceptions.EntityAlreadyExistsException:
            pass
        
        # Task Role
        try:
            task_role = iam.create_role(
                RoleName=f"{app_name}-task-role",
                AssumeRolePolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }]
                })
            )
            # Attach policies to task role
            policies = [
                'arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceRole',
                'arn:aws:iam::aws:policy/AmazonRDSFullAccess',
                'arn:aws:iam::aws:policy/AmazonS3FullAccess',
                'arn:aws:iam::aws:policy/AmazonSQSFullAccess',
                'arn:aws:iam::aws:policy/AmazonSSMFullAccess'
            ]
            for policy in policies:
                iam.attach_role_policy(RoleName=f"{app_name}-task-role", PolicyArn=policy)
        except iam.exceptions.EntityAlreadyExistsException:
            pass
        
        # ECS Instance Role
        try:
            instance_role = iam.create_role(
                RoleName='ecsInstanceRole',
                AssumeRolePolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Service": "ec2.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }]
                })
            )
            policies = [
                'arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role',
                'arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM',
                'arn:aws:iam::aws:policy/AmazonRDSFullAccess',
                'arn:aws:iam::aws:policy/AmazonS3FullAccess',
                'arn:aws:iam::aws:policy/AmazonSSMFullAccess'
            ]
            for policy in policies:
                iam.attach_role_policy(RoleName='ecsInstanceRole', PolicyArn=policy)
        except iam.exceptions.EntityAlreadyExistsException:
            pass
        
        return {
            'task_execution_role': 'ecsTaskExecutionRole',
            'task_role': f"{app_name}-task-role",
            'instance_role': 'ecsInstanceRole'
        }
    
    def create_ecs_infrastructure(self, config):
        """Main method to create complete ECS infrastructure"""
        results = {}
        
        # Create VPC
        if config['create_new_vpc']:
            vpc_result = self.create_vpc(
                config['app_name'], '10.0.0.0/16',
                config['public_subnets'], config['private_subnets']
            )
            results.update(vpc_result)
            vpc_id = vpc_result['vpc_id']
        else:
            vpc_id = config['existing_vpc_id']
        
        # Create Security Groups
        sg_result = self.create_security_groups(
            vpc_id, config['app_name'],
            config.get('create_server_sg', True),
            config.get('create_alb_sg', True),
            config.get('create_rds_sg', True),
            config.get('create_vpn_sg', True)
        )
        results.update(sg_result)
        
        # Create ALB
        alb_result = self.create_alb(
            f"{config['app_name']}-alb", vpc_id,
            results.get('public_subnet_ids', []),
            [sg_result['alb']] if 'alb' in sg_result else []
        )
        results.update(alb_result)
        
        # Create ECR Repository
        ecr_uri = self.create_ecr_repo(config['app_name'])
        results['ecr_uri'] = ecr_uri
        
        # Create IAM Roles
        roles = self.create_iam_roles(config['app_name'])
        results.update(roles)
        
        # Create ECS Cluster with EC2
        # ... (ECS cluster creation code)
        
        return results