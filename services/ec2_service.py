import boto3
from botocore.exceptions import ClientError

class EC2Service:
    def __init__(self, access_key, secret_key, region):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.ec2 = self.session.client('ec2')
        self.region = region
    
    def get_arm64_instance_types(self):
        """Get ARM64 compatible instance types"""
        arm64_instances = [
            {'value': 't4g.micro', 'label': 't4g.micro - 2 vCPU, 1GB RAM'},
            {'value': 't4g.small', 'label': 't4g.small - 2 vCPU, 2GB RAM'},
            {'value': 't4g.medium', 'label': 't4g.medium - 2 vCPU, 4GB RAM'},
            {'value': 't4g.large', 'label': 't4g.large - 2 vCPU, 8GB RAM'},
            {'value': 'm6g.medium', 'label': 'm6g.medium - 1 vCPU, 4GB RAM'},
            {'value': 'm6g.large', 'label': 'm6g.large - 2 vCPU, 8GB RAM'},
            {'value': 'c6g.medium', 'label': 'c6g.medium - 1 vCPU, 2GB RAM'},
            {'value': 'c6g.large', 'label': 'c6g.large - 2 vCPU, 4GB RAM'},
            {'value': 'r6g.medium', 'label': 'r6g.medium - 1 vCPU, 8GB RAM'},
            {'value': 'r6g.large', 'label': 'r6g.large - 2 vCPU, 16GB RAM'}
        ]
        return arm64_instances
    
    def create_key_pair(self, key_name):
        """Create a new key pair and return the private key"""
        try:
            response = self.ec2.create_key_pair(
                KeyName=key_name,
                KeyType='rsa',
                KeyFormat='pem'
            )
            
            # Return both key material and key name
            return {
                'success': True,
                'key_name': key_name,
                'private_key': response['KeyMaterial'],
                'key_id': response['KeyPairId']
            }
            
        except ClientError as e:
            if 'InvalidKeyPair.Duplicate' in str(e):
                raise Exception(f"Key pair '{key_name}' already exists")
            else:
                raise Exception(f"Key pair creation failed: {str(e)}")
    
    def list_key_pairs(self):
        """List all available key pairs"""
        try:
            response = self.ec2.describe_key_pairs()
            key_pairs = []
            for kp in response['KeyPairs']:
                key_pairs.append({
                    'KeyName': kp['KeyName'],
                    'KeyType': kp.get('KeyType', 'rsa'),
                    'KeyPairId': kp.get('KeyPairId', '')
                })
            return key_pairs
        except ClientError as e:
            print(f"Error listing key pairs: {str(e)}")
            return []
    
    def delete_key_pair(self, key_name):
        """Delete a key pair"""
        try:
            self.ec2.delete_key_pair(KeyName=key_name)
            return True
        except ClientError as e:
            print(f"Error deleting key pair: {str(e)}")
            return False