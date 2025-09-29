import boto3
from botocore.exceptions import ClientError, NoCredentialsError

class AWSAuth:
    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key
    
    def validate_credentials(self):
        try:
            # Test with ECR first (since that's what's failing)
            ecr = boto3.client(
                'ecr',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name='ap-south-1'
            )
            
            # Try to get authorization token (this will validate credentials)
            auth_response = ecr.get_authorization_token()
            
            # Also test with STS to get account info
            sts = boto3.client(
                'sts',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            
            response = sts.get_caller_identity()
            account_info = {
                'Account': response['Account'],
                'UserId': response['UserId'],
                'Arn': response['Arn']
            }
            
            return True, account_info
            
        except ClientError as e:
            if "UnrecognizedClientException" in str(e) or "InvalidClientTokenId" in str(e):
                return False, {"error": "Invalid AWS credentials. Please check your access key and secret key."}
            elif "AccessDenied" in str(e):
                return False, {"error": "Access denied. The credentials are valid but don't have sufficient permissions."}
            else:
                return False, {"error": f"AWS error: {str(e)}"}
        except NoCredentialsError:
            return False, {"error": "No AWS credentials found"}
        except Exception as e:
            return False, {"error": f"Unexpected error: {str(e)}"}

    def get_session(self, region='ap-south-1'):
        return boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=region
        )