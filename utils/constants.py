# ECS-optimized AMI IDs for different regions (ARM64)
ECS_AMI_IDS = {
    'us-east-1': 'ami-0c768662d4dd69b20',
    'us-east-2': 'ami-0c768662d4dd69b20', 
    'us-west-2': 'ami-0c768662d4dd69b20',
    'ap-south-1': 'ami-0c768662d4dd69b20',
    'ap-northeast-1': 'ami-0c768662d4dd69b20',
    'eu-west-1': 'ami-0c768662d4dd69b20',
    'eu-central-1': 'ami-0c768662d4dd69b20'
}

# Default instance type
DEFAULT_INSTANCE_TYPE = 't4g.micro'

# Default ports
ALB_PORTS = [80, 443]
SERVER_PORTS = [80, 22, 3306]
RDS_PORTS = [3306]
VPN_PORTS = [10086, 51820]