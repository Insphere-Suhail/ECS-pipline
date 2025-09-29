import boto3
import time

def wait_for_resource(resource_type, check_function, *args, **kwargs):
    """Wait for AWS resource to become available"""
    max_attempts = 30
    delay = 10
    
    for attempt in range(max_attempts):
        try:
            if check_function(*args, **kwargs):
                return True
        except Exception:
            pass
        
        if attempt < max_attempts - 1:
            time.sleep(delay)
    
    return False

def get_account_id(session):
    """Get AWS account ID from session"""
    sts = session.client('sts')
    return sts.get_caller_identity()['Account']