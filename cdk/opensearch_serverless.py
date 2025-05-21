from aws_cdk import (
    App,
    CfnOutput,
    CfnParameter,
    CustomResource,
    Duration,
    Stack,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    custom_resources as cr,
)
from aws_cdk.aws_opensearchserverless import (
    CfnAccessPolicy,
    CfnCollection,
    CfnSecurityPolicy,
)
from constructs import Construct


class OpenSearchServerlessStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Parameters
        iam_user_arn = CfnParameter(
            self,
            "IAMUserArn",
            description="The Arn of the IAM user (or assumed role) running this CloudFormation template.",
            type="String",
        )

        aoss_collection_name = CfnParameter(
            self,
            "AOSSCollectionName",
            default="rag-kb",
            description="Name of the Amazon OpenSearch Service Serverless (AOSS) collection.",
            min_length=1,
            max_length=21,
            allowed_pattern="^[a-z0-9](-*[a-z0-9])*",
            constraint_description="Must be lowercase or numbers with a length of 1-63 characters.",
        )

        # S3 Bucket for Logging
        s3_bucket_for_logging = s3.Bucket(
            self,
            "S3BucketForLogging",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Main S3 Bucket
        s3_bucket = s3.Bucket(
            self,
            "S3Bucket",
            bucket_name=f"{aoss_collection_name.value_as_string}-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            server_access_logs_bucket=s3_bucket_for_logging,
            server_access_logs_prefix="access-logs",
        )

        # S3 Bucket Policies
        s3_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSSLRequestsOnly",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[s3_bucket.bucket_arn, f"{s3_bucket.bucket_arn}/*"],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        s3_bucket_for_logging.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSSLRequestsOnly",
                effect=iam.Effect.DENY,
                principals=[iam.AnyPrincipal()],
                actions=["s3:*"],
                resources=[
                    s3_bucket_for_logging.bucket_arn,
                    f"{s3_bucket_for_logging.bucket_arn}/*",
                ],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        s3_bucket_for_logging.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PutObjectFromSourceBucket",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("logging.s3.amazonaws.com")],
                actions=["s3:PutObject"],
                resources=[f"{s3_bucket_for_logging.bucket_arn}/*"],
                conditions={
                    "ArnLike": {"aws:SourceArn": s3_bucket.bucket_arn},
                    "StringEquals": {"aws:SourceAccount": self.account},
                },
            )
        )

        # Lambda Role for bucket cleanup
        lambda_basic_execution_role = iam.Role(
            self,
            "LambdaBasicExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "S3Access": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=["arn:aws:logs:*:*:*"],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:DeleteObject",
                            ],
                            resources=[f"{s3_bucket.bucket_arn}/*"],
                        ),
                    ]
                )
            },
        )

        # Lambda Function for bucket cleanup
        delete_s3_bucket_lambda = lambda_.Function(
            self,
            "DeleteS3Bucket",
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_inline("""
import json, boto3, logging
import cfnresponse
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info("event: {}".format(event))
    try:
        bucket = event['ResourceProperties']['BucketName']
        logger.info("bucket: {}, event['RequestType']: {}".format(bucket,event['RequestType']))
        if event['RequestType'] == 'Delete':
            s3 = boto3.resource('s3')
            bucket = s3.Bucket(bucket)
            for obj in bucket.objects.filter():
                logger.info("delete obj: {}".format(obj))
                s3.Object(bucket.name, obj.key).delete()

        sendResponseCfn(event, context, cfnresponse.SUCCESS)
    except Exception as e:
        logger.info("Exception: {}".format(e))
        sendResponseCfn(event, context, cfnresponse.FAILED)

def sendResponseCfn(event, context, responseStatus):
    responseData = {}
    responseData['Data'] = {}
    cfnresponse.send(event, context, responseStatus, responseData, "CustomResourcePhysicalID")
            """),
            timeout=Duration.seconds(30),
            role=lambda_basic_execution_role,
            environment={"BUCKET_NAME": s3_bucket.bucket_name},
        )

        # Custom Resource to clean up bucket on delete
        bucket_cleanup_provider = cr.Provider(
            self,
            "CleanupBucketProvider",
            on_event_handler=delete_s3_bucket_lambda,
        )

        bucket_cleanup = CustomResource(
            self,
            "CleanupBucketOnDelete",
            service_token=bucket_cleanup_provider.service_token,
            properties={"BucketName": s3_bucket.bucket_name},
        )
        bucket_cleanup.node.add_dependency(s3_bucket)

        # IAM Role for Bedrock Knowledge Base
        amazon_bedrock_execution_role = iam.Role(
            self,
            "AmazonBedrockExecutionRoleForKnowledgeBase",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            path="/",
        )

        # Update assume role policy with conditions
        amazon_bedrock_execution_role.assume_role_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    principals=[iam.ServicePrincipal("bedrock.amazonaws.com")],
                    actions=["sts:AssumeRole"],
                    conditions={
                        "StringEquals": {"aws:SourceAccount": self.account},
                        "ArnLike": {
                            "AWS:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                        },
                    },
                )
            ]
        )

        # Add S3 read permissions
        amazon_bedrock_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:ListBucket", "s3:Describe*"],
                resources=[
                    f"arn:aws:s3:::{s3_bucket.bucket_name}/*",
                    f"arn:aws:s3:::{s3_bucket.bucket_name}",
                ],
            )
        )

        # Add AOSS API access
        amazon_bedrock_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["aoss:APIAccessAll"],
                resources=[
                    f"arn:aws:aoss:{self.region}:{self.account}:collection/*"
                ],
            )
        )

        # Add Bedrock model access
        amazon_bedrock_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:ListCustomModels"],
                resources=["*"],
            )
        )
        amazon_bedrock_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/*"
                ],
            )
        )

        # OpenSearchServerless Encryption Policy
        encryption_policy = CfnSecurityPolicy(
            self,
            "EncryptionPolicy",
            name=f"{aoss_collection_name.value_as_string}-security-policy",
            type="encryption",
            description="Encryption policy for AOSS collection",
            policy=f'{{"Rules":[{{"ResourceType":"collection","Resource":["collection/{aoss_collection_name.value_as_string}"]}}],"AWSOwnedKey":true}}',
        )

        # OpenSearchServerless Collection
        collection = CfnCollection(
            self,
            "Collection",
            name=aoss_collection_name.value_as_string,
            type="VECTORSEARCH",
            description="Collection to holds vector search data",
        )
        collection.add_depends_on(encryption_policy)

        # OpenSearchServerless Network Policy
        network_policy = CfnSecurityPolicy(
            self,
            "NetworkPolicy",
            name=f"{aoss_collection_name.value_as_string}-network-policy",
            type="network",
            description="Network policy for AOSS collection",
            policy=f'[{{"Rules":[{{"ResourceType":"collection","Resource":["collection/{aoss_collection_name.value_as_string}"]}},'
            f'{{"ResourceType":"dashboard","Resource":["collection/{aoss_collection_name.value_as_string}"]}}],'
            f'"AllowFromPublic":true}}]',
        )

        # OpenSearchServerless Data Access Policy
        data_access_policy = CfnAccessPolicy(
            self,
            "DataAccessPolicy",
            name=f"{aoss_collection_name.value_as_string}-access-policy",
            type="data",
            description="Access policy for AOSS collection",
            policy=f'[{{"Description":"Access for cfn user","Rules":[{{"ResourceType":"index","Resource":["index/*/*"],"Permission":["aoss:*"]}},'
            f'{{"ResourceType":"collection","Resource":["collection/quickstart"],"Permission":["aoss:*"]}}],'
            f'"Principal":["{iam_user_arn.value_as_string}", "{amazon_bedrock_execution_role.role_arn}"]}}]',
        )

        # Outputs
        CfnOutput(
            self,
            "S3Bucket",
            value=s3_bucket.bucket_arn,
            export_name="S3BucketARN",
        )

        CfnOutput(
            self,
            "S3BucketName",
            value=s3_bucket.bucket_name,
            export_name="S3BucketName",
        )

        CfnOutput(
            self,
            "DashboardURL",
            value=collection.attr_dashboard_endpoint,
            export_name="OSCollectionEndpoint",
        )

        CfnOutput(
            self,
            "AmazonBedrockExecutionRoleForKnowledgeBase",
            value=amazon_bedrock_execution_role.role_arn,
            export_name="BedrockKBARN",
        )

        CfnOutput(
            self,
            "CollectionARN",
            value=collection.attr_arn,
            export_name="CollectionARN",
        )


app = App()
OpenSearchServerlessStack(
    app,
    "OpenSearchServerlessStack",
    description="Template to provison Opensearch Serverless collection and S3 Bucket",
)
app.synth()
