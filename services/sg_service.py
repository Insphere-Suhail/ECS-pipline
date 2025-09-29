import boto3
from botocore.exceptions import ClientError

class SecurityGroupService:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.ec2 = self.session.client('ec2')
    
    def list_security_groups(self, vpc_id):
        try:
            filters = []
            if vpc_id:
                filters.append({'Name': 'vpc-id', 'Values': [vpc_id]})
            
            response = self.ec2.describe_security_groups(Filters=filters)
            sgs = []
            for sg in response['SecurityGroups']:
                sg_info = {
                    'GroupId': sg['GroupId'],
                    'GroupName': sg['GroupName'],
                    'Description': sg.get('Description', ''),
                    'VpcId': sg['VpcId']
                }
                sgs.append(sg_info)
            return sgs
        except ClientError as e:
            return {'error': str(e)}
    
    def list_key_pairs(self):
        try:
            response = self.ec2.describe_key_pairs()
            key_pairs = []
            for kp in response['KeyPairs']:
                key_pairs.append({
                    'KeyName': kp['KeyName'],
                    'KeyType': kp.get('KeyType', 'rsa')
                })
            return key_pairs
        except ClientError as e:
            return {'error': str(e)}
    
    def create_alb_sg(self, infra_name, vpc_id, existing_sg_id=None):
        if existing_sg_id:
            return existing_sg_id
            
        try:
            sg_name = f"{infra_name}-alb-sg"
            response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description=f"ALB Security Group for {infra_name}",
                VpcId=vpc_id,
                TagSpecifications=[{
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            sg_id = response['GroupId']
            
            # Add inbound rules for ALB - ONLY HTTP and HTTPS from 0.0.0.0/0
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            
            print(f"✅ ALB Security Group created: {sg_id}")
            print(f"   - Inbound: HTTP (80) from 0.0.0.0/0")
            print(f"   - Inbound: HTTPS (443) from 0.0.0.0/0")
            
            return sg_id
            
        except ClientError as e:
            raise Exception(f"ALB Security Group creation failed: {str(e)}")
    
    def create_server_sg(self, infra_name, vpc_id, alb_sg_id=None, vpn_sg_id=None, existing_sg_id=None):
        if existing_sg_id:
            return existing_sg_id
            
        try:
            sg_name = f"{infra_name}-server-sg"
            response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description=f"Server Security Group for {infra_name}",
                VpcId=vpc_id,
                TagSpecifications=[{
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            sg_id = response['GroupId']
            
            # Build IP permissions - HTTP/HTTPS from ALB SG + SSH from VPN SG
            ip_permissions = []
            
            # HTTP/HTTPS access from ALB SG
            if alb_sg_id:
                ip_permissions.extend([
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'UserIdGroupPairs': [{'GroupId': alb_sg_id}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'UserIdGroupPairs': [{'GroupId': alb_sg_id}]
                    }
                ])
            
            # SSH access from VPN SG
            if vpn_sg_id:
                ip_permissions.append({
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'UserIdGroupPairs': [{'GroupId': vpn_sg_id}]
                })
            
            if ip_permissions:
                self.ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=ip_permissions
                )
            
            print(f"✅ Server Security Group created: {sg_id}")
            if alb_sg_id:
                print(f"   - Inbound: HTTP (80) from ALB SG: {alb_sg_id}")
                print(f"   - Inbound: HTTPS (443) from ALB SG: {alb_sg_id}")
            if vpn_sg_id:
                print(f"   - Inbound: SSH (22) from VPN SG: {vpn_sg_id}")
            
            return sg_id
            
        except ClientError as e:
            raise Exception(f"Server Security Group creation failed: {str(e)}")
    
    def create_rds_sg(self, infra_name, vpc_id, server_sg_id=None, vpn_sg_id=None, existing_sg_id=None):
        if existing_sg_id:
            return existing_sg_id
            
        try:
            sg_name = f"{infra_name}-rds-sg"
            response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description=f"RDS Security Group for {infra_name}",
                VpcId=vpc_id,
                TagSpecifications=[{
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            sg_id = response['GroupId']
            
            # Build IP permissions for RDS - MySQL from Server SG and VPN SG
            ip_permissions = []
            
            # MySQL access from Server SG
            if server_sg_id:
                ip_permissions.append({
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'UserIdGroupPairs': [{'GroupId': server_sg_id}]
                })
            
            # MySQL access from VPN SG
            if vpn_sg_id:
                ip_permissions.append({
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'UserIdGroupPairs': [{'GroupId': vpn_sg_id}]
                })
            
            if ip_permissions:
                self.ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=ip_permissions
                )
            
            print(f"✅ RDS Security Group created: {sg_id}")
            if server_sg_id:
                print(f"   - Inbound: MySQL (3306) from Server SG: {server_sg_id}")
            if vpn_sg_id:
                print(f"   - Inbound: MySQL (3306) from VPN SG: {vpn_sg_id}")
            
            return sg_id
            
        except ClientError as e:
            raise Exception(f"RDS Security Group creation failed: {str(e)}")
    
    def create_vpn_sg(self, infra_name, vpc_id, existing_sg_id=None):
        if existing_sg_id:
            return existing_sg_id
            
        try:
            sg_name = f"{infra_name}-vpn-sg"
            response = self.ec2.create_security_group(
                GroupName=sg_name,
                Description=f"VPN Security Group for {infra_name}",
                VpcId=vpc_id,
                TagSpecifications=[{
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                }]
            )
            sg_id = response['GroupId']
            
            # Add inbound rules for VPN - ONLY from 0.0.0.0/0
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 10086,
                        'ToPort': 10086,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'udp',
                        'FromPort': 51820,
                        'ToPort': 51820,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            
            print(f"✅ VPN Security Group created: {sg_id}")
            print(f"   - Inbound: TCP (10086) from 0.0.0.0/0")
            print(f"   - Inbound: UDP (51820) from 0.0.0.0/0")
            
            return sg_id
            
        except ClientError as e:
            raise Exception(f"VPN Security Group creation failed: {str(e)}")