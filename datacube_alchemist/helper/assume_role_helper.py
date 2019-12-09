import boto3

def role_arn_to_session(**args):
    """ Create boto3 session using federated access
        Usage :
            params = {
                "RoleArn": 'arn:aws:iam::012345678901:role/example-role',
                "RoleSessionName": 'ExampleSessionName',
                "WebIdentityToken": 'ExampleToken',
                "DurationSeconds": 3600,
            }
            session = role_arn_to_session(**params)
            client = session.client('sqs')
    """
    sts_client = boto3.client('sts')
    response=sts_client.assume_role_with_web_identity(**args).get("Credentials")
    return boto3.Session(
        aws_access_key_id=response.get("AccessKeyId"),
        aws_secret_access_key=response.get("SecretAccessKey"),
        aws_session_token=response.get("SessionToken")
    )

def refresh_credentials(**args):
    """ Refresh tokens by calling assume_role_with_web_identity again
        Usage :
            params = {
                "RoleArn": 'arn:aws:iam::012345678901:role/example-role',
                "RoleSessionName": 'ExampleSessionName',
                "WebIdentityToken": 'ExampleToken',
                "DurationSeconds": 3600,
            }
            creds = refresh_credentials(**params)
    """
    sts_client = boto3.client('sts')
    response=sts_client.assume_role_with_web_identity(**args).get("Credentials")
    credentials = {
        "access_key": response.get("AccessKeyId"),
        "secret_key": response.get("SecretAccessKey"),
        "token": response.get("SessionToken"),
        "expiry_time": response.get("Expiration").isoformat(),
    }
    return credentials