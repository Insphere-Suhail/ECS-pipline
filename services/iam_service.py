import boto3
import json
import time
from botocore.exceptions import ClientError

class IAMService:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.iam = self.session.client('iam')
    
    def get_account_id(self):
        sts = self.session.client('sts')
        return sts.get_caller_identity()['Account']
    
    def create_task_role(self, infra_name):
        try:
            role_name = f"ecsTaskRole-{infra_name}"
            
            # Check if role already exists
            try:
                response = self.iam.get_role(RoleName=role_name)
                print(f"✅ Task role already exists: {role_name}")
                return response['Role']['Arn']
            except ClientError:
                pass  # Role doesn't exist, create it
            
            # Create role with proper trust policy for ECS tasks
            assume_role_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                Description=f"ECS Task Role for {infra_name}",
                Tags=[
                    {'Key': 'Name', 'Value': role_name},
                    {'Key': 'Infra', 'Value': infra_name},
                    {'Key': 'Service', 'Value': 'ECS'}
                ]
            )
            role_arn = response['Role']['Arn']
            
            # Attach the exact policies you specified
            policies = [
                'arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser',
                'arn:aws:iam::aws:policy/AmazonRDSFullAccess',
                'arn:aws:iam::aws:policy/AmazonS3FullAccess',
                'arn:aws:iam::aws:policy/AmazonSQSFullAccess',
                'arn:aws:iam::aws:policy/AmazonSSMFullAccess',
                'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'
            ]
            
            for policy_arn in policies:
                try:
                    self.iam.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                    print(f"✅ Attached policy {policy_arn.split('/')[-1]} to {role_name}")
                except ClientError as e:
                    print(f"⚠️ Could not attach policy {policy_arn}: {str(e)}")
            
            print(f"✅ Task role created: {role_arn}")
            return role_arn
            
        except ClientError as e:
            raise Exception(f"❌ Task role creation failed: {str(e)}")
    
    def create_execution_role(self, infra_name):
        try:
            role_name = f"ecsTaskExecutionRole-{infra_name}"
            
            # Check if role already exists
            try:
                response = self.iam.get_role(RoleName=role_name)
                print(f"✅ Execution role already exists: {role_name}")
                return response['Role']['Arn']
            except ClientError:
                pass  # Role doesn't exist, create it
            
            # Create role
            assume_role_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            
            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                Description=f"ECS Task Execution Role for {infra_name}",
                Tags=[
                    {'Key': 'Name', 'Value': role_name},
                    {'Key': 'Infra', 'Value': infra_name},
                    {'Key': 'Service', 'Value': 'ECS'}
                ]
            )
            role_arn = response['Role']['Arn']
            
            # Attach policies - AmazonECSTaskExecutionRolePolicy provides ECR access
            policies = [
                'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy',
                'arn:aws:iam::aws:policy/AmazonS3FullAccess',
                'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'
            ]
            
            for policy_arn in policies:
                try:
                    self.iam.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                    print(f"✅ Attached policy {policy_arn.split('/')[-1]} to {role_name}")
                except ClientError as e:
                    print(f"⚠️ Could not attach policy {policy_arn}: {str(e)}")
            
            print(f"✅ Execution role created: {role_arn}")
            return role_arn
            
        except ClientError as e:
            raise Exception(f"❌ Execution role creation failed: {str(e)}")
    
    def create_instance_role(self, infra_name):
        """Create EC2 instance role and return the ROLE NAME (not ARN)"""
        try:
            role_name = f"ecsInstanceRole-{infra_name}"
            instance_profile_name = role_name
            
            # Check if role already exists
            try:
                self.iam.get_role(RoleName=role_name)
                print(f"✅ IAM role already exists: {role_name}")
            except ClientError:
                # Create the role
                trust_policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "ec2.amazonaws.com"
                            },
                            "Action": "sts:AssumeRole"
                        }
                    ]
                }
                
                self.iam.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f"ECS Instance role for {infra_name}",
                    Tags=[
                        {'Key': 'Name', 'Value': role_name},
                        {'Key': 'Infra', 'Value': infra_name}
                    ]
                )
                print(f"✅ IAM role created: {role_name}")
            
            # Check if instance profile already exists
            try:
                self.iam.get_instance_profile(InstanceProfileName=instance_profile_name)
                print(f"✅ Instance profile already exists: {instance_profile_name}")
            except ClientError:
                # Create instance profile
                self.iam.create_instance_profile(
                    InstanceProfileName=instance_profile_name
                )
                print(f"✅ Instance profile created: {instance_profile_name}")
                
                # Wait a bit before adding role
                time.sleep(5)
                
                # Add role to instance profile
                self.iam.add_role_to_instance_profile(
                    InstanceProfileName=instance_profile_name,
                    RoleName=role_name
                )
                print(f"✅ Role added to instance profile: {role_name}")
            
            # **SIMPLIFIED POLICY ATTACHMENT - Only essential policies**
            required_policies = [
                # ECS Container Service role for EC2 instances - THIS IS THE KEY POLICY
                'arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role',
                
                # SSM for instance management
                'arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM',
                
                # ECR read-only access for pulling images
                'arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly'
            ]
            
            # **REMOVED: Don't attach CloudWatchLogsFullAccess and AmazonECSTaskExecutionRolePolicy**
            # These are for task execution, not instance role
            
            # Attach managed policies
            for policy_arn in required_policies:
                try:
                    self.iam.attach_role_policy(
                        RoleName=role_name,
                        PolicyArn=policy_arn
                    )
                    print(f"✅ Attached policy: {policy_arn.split('/')[-1]}")
                except ClientError as e:
                    print(f"⚠️ Could not attach policy {policy_arn}: {e}")
            
            # **REMOVED: Don't add inline policy - the managed policies cover everything needed**
            
            # Wait for IAM propagation
            print("⏳ Waiting for IAM role propagation...")
            time.sleep(15)
            
            # **CHANGED: Return the ROLE NAME, not ARN**
            print(f"✅ Instance role setup completed: {role_name}")
            return role_name  # Return name, not ARN
            
        except ClientError as e:
            raise Exception(f"❌ Instance role creation failed: {str(e)}")
    
    def get_instance_profile_arn(self, role_name):
        """Get instance profile ARN for a given role name"""
        try:
            instance_profile_name = role_name
            response = self.iam.get_instance_profile(
                InstanceProfileName=instance_profile_name
            )
            return response['InstanceProfile']['Arn']
        except ClientError as e:
            raise Exception(f"Could not get instance profile ARN: {str(e)}")