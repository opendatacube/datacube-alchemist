import boto3
from botocore.session import get_session
from botocore.credentials import RefreshableCredentials

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


def get_autorefresh_session(**args):
    """ return auto referesh session using assume role
    Usage:
        params = {
            "DurationSeconds": os.getenv('SESSION_DURATION', 3600),
            "RoleArn": os.getenv('AWS_ROLE_ARN'),
            "RoleSessionName": os.getenv('AWS_SESSION_NAME', 'test_session'),
            "WebIdentityToken": open(os.getenv('AWS_WEB_IDENTITY_TOKEN_FILE')).read(),
        }
        session = autorefresh_session(**params)
        client = session.client('sqs')
    """
    session = get_session()
    session._credentials = RefreshableCredentials.create_from_metadata(
        metadata=refresh_credentials(**args),
        refresh_using=refresh_credentials,
        method="sts-assume-role-with-web-identity",
    )
    return boto3.Session(botocore_session=session)


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