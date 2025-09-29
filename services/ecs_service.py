import boto3
import json
import base64
import time
from botocore.exceptions import ClientError

class ECSService:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.ecs = self.session.client('ecs')
        self.ec2 = self.session.client('ec2')
        self.autoscaling = self.session.client('autoscaling')
        self.ssm = self.session.client('ssm')
        self.iam = self.session.client('iam')
        self.cloudformation = self.session.client('cloudformation')
        self.region = region
        self.account_id = self._get_account_id()
    
    def create_task_definition(self, infra_name, ecr_repo_uri, task_role_arn, execution_role_arn):
        try:
            task_def = {
                "family": infra_name,
                "networkMode": "awsvpc",
                "requiresCompatibilities": ["EC2"],
                "cpu": "256",
                "memory": "512",
                "executionRoleArn": execution_role_arn,
                "taskRoleArn": task_role_arn,
                "runtimePlatform": {
                    "cpuArchitecture": "ARM64",
                    "operatingSystemFamily": "LINUX"
                },
                "containerDefinitions": [
                    {
                        "name": infra_name,
                        "image": f"{ecr_repo_uri}:latest",
                        "cpu": 128,
                        "memory": 256,
                        "essential": True,
                        "portMappings": [
                            {
                                "containerPort": 80,
                                "hostPort": 80,
                                "protocol": "tcp"
                            }
                        ],
                        "logConfiguration": {
                            "logDriver": "awslogs",
                            "options": {
                                "awslogs-group": f"/ecs/{infra_name}",
                                "awslogs-region": self.region,
                                "awslogs-stream-prefix": "ecs"
                            }
                        }
                    }
                ]
            }
            
            response = self.ecs.register_task_definition(**task_def)
            print(f"✅ Task Definition created")
            return response['taskDefinition']['taskDefinitionArn']
            
        except ClientError as e:
            raise Exception(f"Task definition creation failed: {str(e)}")
    
    def create_cluster(self, infra_name, vpc_id, private_subnets, security_group_id, instance_role_name, key_pair=None, instance_type='t4g.micro'):
        try:
            # **EXACT CONFIGURATION AS AWS CONSOLE**
            # Create ECS cluster with exact same settings as console
            self.ecs.create_cluster(
                clusterName=infra_name,
                settings=[
                    {
                        'name': 'containerInsights',
                        'value': 'disabled'  # Same as console default
                    }
                ],
                configuration={
                    'executeCommandConfiguration': {
                        'logging': 'DEFAULT'
                    }
                }
            )
            print(f"✅ ECS Cluster created: {infra_name}")
            
            # Get or create instance profile for the role
            instance_profile_arn = self._get_or_create_instance_profile(instance_role_name)
            
            # Create the exact same infrastructure as console
            self._create_console_style_infrastructure(infra_name, vpc_id, private_subnets, security_group_id, instance_profile_arn, key_pair, instance_type)
            
            return f"arn:aws:ecs:{self.region}:{self.account_id}:cluster/{infra_name}"
            
        except ClientError as e:
            raise Exception(f"Cluster creation failed: {str(e)}")
    
    def _get_or_create_instance_profile(self, role_name):
        """Get or create instance profile for the given role"""
        try:
            instance_profile_name = role_name
            instance_profile_arn = f"arn:aws:iam::{self.account_id}:instance-profile/{instance_profile_name}"
            
            # Check if instance profile exists
            try:
                response = self.iam.get_instance_profile(InstanceProfileName=instance_profile_name)
                print(f"✅ Using existing instance profile: {instance_profile_name}")
                return response['InstanceProfile']['Arn']
            except self.iam.exceptions.NoSuchEntityException:
                # Create instance profile
                print(f"🔄 Creating instance profile: {instance_profile_name}")
                self.iam.create_instance_profile(InstanceProfileName=instance_profile_name)
                
                # Wait for instance profile to be available
                time.sleep(5)
                
                # Add role to instance profile
                self.iam.add_role_to_instance_profile(
                    InstanceProfileName=instance_profile_name,
                    RoleName=role_name
                )
                
                # Wait for propagation
                time.sleep(10)
                
                print(f"✅ Instance profile created: {instance_profile_name}")
                return instance_profile_arn
                
        except ClientError as e:
            raise Exception(f"Instance profile creation failed: {str(e)}")
    
    def _create_console_style_infrastructure(self, infra_name, vpc_id, private_subnets, security_group_id, instance_profile_arn, key_pair, instance_type):
        """Create infrastructure exactly like AWS Console CloudFormation template"""
        try:
            # **EXACT SAME USER DATA AS CONSOLE**
            user_data = f"""#!/bin/bash 
echo ECS_CLUSTER={infra_name} >> /etc/ecs/ecs.config;
echo ECS_BACKEND_HOST=https://ecs.{self.region}.amazonaws.com >> /etc/ecs/ecs.config;
"""
            
            # Get the exact same AMI that console uses
            ami_id = self._get_console_ecs_optimized_ami()
            
            # Create Launch Template (EXACT SAME AS CONSOLE)
            launch_template_data = {
                'ImageId': ami_id,
                'InstanceType': instance_type,  # Use the selected instance type
                'SecurityGroupIds': [security_group_id],
                'IamInstanceProfile': {
                    'Arn': instance_profile_arn
                },
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/xvda',
                        'Ebs': {
                            'VolumeSize': 50  # Same as console
                        }
                    }
                ],
                'UserData': base64.b64encode(user_data.encode()).decode(),
                'MetadataOptions': {
                    'HttpTokens': 'required',
                    'HttpEndpoint': 'enabled'
                }
            }
            
            # Add key pair if provided (same as console)
            if key_pair:
                launch_template_data['KeyName'] = key_pair
            
            # Create Launch Template
            self.ec2.create_launch_template(
                LaunchTemplateName=f"{infra_name}-lt",
                LaunchTemplateData=launch_template_data
            )
            print(f"✅ Launch Template created: {infra_name}-lt")
            
            # Wait for launch template
            time.sleep(10)
            
            # Create Auto Scaling Group (EXACT SAME AS CONSOLE)
            asg_name = f"{infra_name}-asg"
            self.autoscaling.create_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                LaunchTemplate={
                    'LaunchTemplateName': f"{infra_name}-lt",
                    'Version': '$Latest'
                },
                MinSize=1,        # Same as console
                MaxSize=5,        # Same as console  
                DesiredCapacity=1, # Same as console
                VPCZoneIdentifier=','.join(private_subnets),
                HealthCheckType='EC2',
                HealthCheckGracePeriod=300,
                NewInstancesProtectedFromScaleIn=False,
                Tags=[
                    {
                        'Key': 'Name',
                        'PropagateAtLaunch': True,
                        'Value': f"ECS Instance - {infra_name}"  # Same format as console
                    }
                ]
            )
            print(f"✅ Auto Scaling Group created: {asg_name}")
            
            # Create Capacity Provider (EXACT SAME AS CONSOLE)
            self._create_console_capacity_provider(infra_name, asg_name)
            
            # Associate capacity provider with cluster (EXACT SAME AS CONSOLE)
            self._associate_console_capacity_providers(infra_name, asg_name)
            
            # Wait for instances to register
            print("⏳ Waiting for ASG instances to register with ECS cluster...")
            instances_registered = self._wait_for_instances_registered(infra_name)
            
            if instances_registered:
                print("✅ Instances successfully registered with ECS cluster")
            else:
                print("⚠️  Instances not registered yet. They should register automatically.")
                self._debug_instance_status(infra_name)
            
        except ClientError as e:
            raise Exception(f"Infrastructure creation failed: {str(e)}")
    
    def _create_console_capacity_provider(self, infra_name, asg_name):
        """Create Capacity Provider exactly like console"""
        try:
            capacity_provider_name = f"{infra_name}-cp"
            
            # Get ASG ARN
            asg_response = self.autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            
            if not asg_response['AutoScalingGroups']:
                raise Exception(f"Auto Scaling Group {asg_name} not found")
            
            asg_arn = asg_response['AutoScalingGroups'][0]['AutoScalingGroupARN']
            
            print(f"🔄 Creating Capacity Provider with ASG: {asg_name}")
            
            # EXACT SAME CONFIGURATION AS CONSOLE
            self.ecs.create_capacity_provider(
                name=capacity_provider_name,
                autoScalingGroupProvider={
                    'autoScalingGroupArn': asg_arn,
                    'managedScaling': {
                        'status': 'ENABLED',      # Same as console
                        'targetCapacity': 100     # Same as console
                    },
                    'managedTerminationProtection': 'DISABLED'  # Same as console
                }
            )
            print(f"✅ Capacity Provider created: {capacity_provider_name}")
            
            time.sleep(10)
            
        except ClientError as e:
            raise Exception(f"Capacity provider creation failed: {str(e)}")
    
    def _associate_console_capacity_providers(self, infra_name, asg_name):
        """Associate capacity providers exactly like console"""
        try:
            capacity_provider_name = f"{infra_name}-cp"
            
            # EXACT SAME CONFIGURATION AS CONSOLE
            # Console includes FARGATE, FARGATE_SPOT and our ASG capacity provider
            self.ecs.put_cluster_capacity_providers(
                cluster=infra_name,
                capacityProviders=[
                    'FARGATE',
                    'FARGATE_SPOT', 
                    capacity_provider_name
                ],
                defaultCapacityProviderStrategy=[
                    {
                        'capacityProvider': capacity_provider_name,
                        'weight': 1,      # Same as console
                        'base': 0         # Same as console
                    }
                ]
            )
            print(f"✅ Capacity Providers associated with cluster: {infra_name}")
            print(f"   - FARGATE")
            print(f"   - FARGATE_SPOT") 
            print(f"   - {capacity_provider_name} (Default)")
            
        except ClientError as e:
            raise Exception(f"Capacity provider association failed: {str(e)}")
    
    def _get_console_ecs_optimized_ami(self):
        """Get the EXACT same AMI that console uses"""
        try:
            # Console uses Amazon Linux 2023 ARM64
            response = self.ssm.get_parameter(
                Name='/aws/service/ecs/optimized-ami/amazon-linux-2023/arm64/recommended/image_id'
            )
            ami_id = response['Parameter']['Value']
            print(f"✅ Using Console ECS-optimized AMI (AL2023 ARM64): {ami_id}")
            return ami_id
        except ClientError as e:
            print(f"⚠️  Could not get AMI from SSM: {str(e)}")
            # Fallback to known AMIs
            amis = {
                'ap-south-1': 'ami-05494a57c45f84170',  # AL2023 ARM64 for Mumbai
                'us-east-1': 'ami-0c02fb55956c7d316',
                'us-west-2': 'ami-0c6c53a1c9c1c9c1c'
            }
            ami_id = amis.get(self.region, 'ami-05494a57c45f84170')
            print(f"✅ Using fallback ECS-optimized AMI: {ami_id}")
            return ami_id
    
    def _wait_for_instances_registered(self, cluster_name, timeout=600):
        """Wait for ASG instances to register with the cluster"""
        start_time = time.time()
        instances_registered = False
        
        print(f"⏳ Waiting up to {timeout} seconds for instances to register with cluster {cluster_name}...")
        
        while time.time() - start_time < timeout:
            try:
                response = self.ecs.list_container_instances(cluster=cluster_name)
                
                if response['containerInstanceArns']:
                    instance_count = len(response['containerInstanceArns'])
                    print(f"✅ {instance_count} instance(s) registered with cluster")
                    
                    # Get instance details
                    instances_response = self.ecs.describe_container_instances(
                        cluster=cluster_name,
                        containerInstances=response['containerInstanceArns']
                    )
                    
                    for instance in instances_response['containerInstances']:
                        ec2_instance_id = instance['ec2InstanceId']
                        status = instance['status']
                        agent_connected = instance['agentConnected']
                        running_tasks_count = instance['runningTasksCount']
                        capacity_provider = instance.get('capacityProviderName', 'N/A')
                        print(f"   - Instance {ec2_instance_id}:")
                        print(f"     Status: {status}, Agent: {agent_connected}")
                        print(f"     Running Tasks: {running_tasks_count}")
                        print(f"     Capacity Provider: {capacity_provider}")
                    
                    instances_registered = True
                    break
                else:
                    # Check ASG instances
                    asg_instances = self._check_asg_instances(cluster_name)
                    if asg_instances:
                        print(f"⏳ ASG has {len(asg_instances)} instances but they haven't registered with ECS yet...")
                        time.sleep(30)
                    else:
                        print("⏳ Waiting for ASG to launch instances...")
                        time.sleep(30)
                    
            except ClientError as e:
                if "Cluster not found" in str(e):
                    print("⏳ Cluster not ready yet, waiting...")
                    time.sleep(30)
                else:
                    print(f"⏳ Error checking instances: {str(e)}")
                    time.sleep(30)
        
        return instances_registered
    
    def _check_asg_instances(self, cluster_name):
        """Check ASG instances status"""
        try:
            asg_response = self.autoscaling.describe_auto_scaling_groups()
            
            cluster_asgs = []
            for asg in asg_response['AutoScalingGroups']:
                for tag in asg.get('Tags', []):
                    if tag['Key'] == 'Name' and f"ECS Instance - {cluster_name}" in tag['Value']:
                        cluster_asgs.append(asg)
                        break
            
            return cluster_asgs
            
        except ClientError as e:
            print(f"Error checking ASG instances: {str(e)}")
            return []
    
    def _debug_instance_status(self, cluster_name):
        """Debug instance status"""
        try:
            print("🔍 Debugging instance registration...")
            
            asg_response = self.autoscaling.describe_auto_scaling_groups()
            for asg in asg_response['AutoScalingGroups']:
                for tag in asg.get('Tags', []):
                    if tag['Key'] == 'Name' and f"ECS Instance - {cluster_name}" in tag['Value']:
                        print(f"ASG {asg['AutoScalingGroupName']} has {len(asg['Instances'])} instances:")
                        for instance in asg['Instances']:
                            instance_id = instance['InstanceId']
                            print(f"  - Instance {instance_id}: {instance['LifecycleState']}")
                            
                            try:
                                ec2_response = self.ec2.describe_instances(InstanceIds=[instance_id])
                                if ec2_response['Reservations']:
                                    ec2_instance = ec2_response['Reservations'][0]['Instances'][0]
                                    state = ec2_instance['State']['Name']
                                    launch_time = ec2_instance['LaunchTime']
                                    print(f"    EC2 State: {state}, Launched: {launch_time}")
                                    
                            except ClientError as e:
                                print(f"    Error checking EC2 instance: {str(e)}")
            
        except ClientError as e:
            print(f"Error during instance debugging: {str(e)}")
    
    def _get_account_id(self):
        sts = self.session.client('sts')
        return sts.get_caller_identity()['Account']
    
    def create_service(self, infra_name, cluster_arn, task_def_arn, private_subnets, security_group_id, alb_arn=None, target_group_arn=None):
        try:
            cluster_name = infra_name
            
            # Use the capacity provider strategy (same as console default)
            service_config = {
                'cluster': cluster_name,
                'serviceName': f"{infra_name}-service",
                'taskDefinition': task_def_arn.split('/')[-1],
                'desiredCount': 1,
                'capacityProviderStrategy': [
                    {
                        'capacityProvider': f"{infra_name}-cp",
                        'weight': 1,
                        'base': 0  # Same as console
                    }
                ],
                'networkConfiguration': {
                    'awsvpcConfiguration': {
                        'subnets': private_subnets,
                        'securityGroups': [security_group_id],
                        'assignPublicIp': 'DISABLED'
                    }
                },
                'healthCheckGracePeriodSeconds': 60,
                'schedulingStrategy': 'REPLICA',
                'enableECSManagedTags': True,
                'propagateTags': 'SERVICE'
            }
            
            if target_group_arn:
                service_config['loadBalancers'] = [{
                    'targetGroupArn': target_group_arn,
                    'containerName': infra_name,
                    'containerPort': 80
                }]
                service_config['healthCheckGracePeriodSeconds'] = 300
            
            response = self.ecs.create_service(**service_config)
            print(f"✅ ECS Service created with Capacity Provider strategy")
            
            return response['service']['serviceArn']
            
        except ClientError as e:
            raise Exception(f"Service creation failed: {str(e)}")