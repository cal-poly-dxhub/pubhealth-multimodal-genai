#!/usr/bin/env python3
from aws_cdk import (
    CfnOutput,
    CfnParameter,
    CfnResource,
    CustomResource,
    Duration,
    Fn,
    Stack,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from constructs import Construct


class RagKnowledgeBaseStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameters
        knowledge_base_name = CfnParameter(
            self,
            "KnowledgeBaseName",
            default="rag-kb",
            description="The name of the knowledge base.",
        ).value_as_string

        knowledge_base_description = CfnParameter(
            self,
            "KnowledgeBaseDescription",
            default="Answer based only on information contained in knowledge base.",
            description="The description of the knowledge base.",
        ).value_as_string

        aoss_index_name = CfnParameter(
            self,
            "AOSSIndexName",
            default="rag-readthedocs-io",
            description="Name of the vector index in the Amazon OpenSearch Service Serverless (AOSS) collection.",
        ).value_as_string

        # Import values from other stacks
        s3_bucket_arn = Fn.import_value("S3BucketARN")
        s3_bucket_name = Fn.import_value("S3BucketName")
        bedrock_kb_arn = Fn.import_value("BedrockKBARN")
        collection_arn = Fn.import_value("CollectionARN")

        # Create IAM Role for Lambda custom resource
        lambda_iam_role = iam.Role(
            self,
            "LambdaIAMRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        lambda_iam_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetBucketNotification",
                    "s3:PutBucketNotification",
                ],
                resources=[s3_bucket_arn],
            )
        )

        lambda_iam_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:*"],
            )
        )

        lambda_iam_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/customresource-lambda-functions:*"
                ],
            )
        )

        # Create the CustomResourceLambdaFunction
        bucket_manager = lambda_.Function(
            self,
            "BucketMmgtFunction",
            function_name="bucket-manager",
            handler="bucket_manager.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../src/bucket_manager"),
            role=lambda_iam_role,
            timeout=Duration.seconds(50),
        )

        # Create KBSyncRole
        kb_sync_role = iam.Role(
            self,
            "KBSyncRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        kb_sync_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:ListBucket", "s3:PutObject"],
                resources=[
                    f"arn:aws:s3:::rag-kb-{self.account}",
                    f"arn:aws:s3:::rag-kb-{self.account}/*",
                ],
            )
        )

        kb_sync_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:*"],
            )
        )

        kb_sync_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/kbsync-demo-functions:*"
                ],
            )
        )

        # Create Knowledge Base resource
        knowledge_base = CfnResource(
            self,
            "KnowledgeBaseWithAoss",
            type="AWS::Bedrock::KnowledgeBase",
            properties={
                "Name": knowledge_base_name,
                "Description": knowledge_base_description,
                "RoleArn": bedrock_kb_arn,
                "KnowledgeBaseConfiguration": {
                    "Type": "VECTOR",
                    "VectorKnowledgeBaseConfiguration": {
                        "EmbeddingModelArn": f"arn:{self.partition}:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1"
                    },
                },
                "StorageConfiguration": {
                    "Type": "OPENSEARCH_SERVERLESS",
                    "OpensearchServerlessConfiguration": {
                        "CollectionArn": collection_arn,
                        "VectorIndexName": aoss_index_name,
                        "FieldMapping": {
                            "VectorField": "vector",
                            "TextField": "text",
                            "MetadataField": "metadata",
                        },
                    },
                },
            },
        )

        # Create the data source
        data_source = CfnResource(
            self,
            "SampleDataSource",
            type="AWS::Bedrock::DataSource",
            properties={
                "KnowledgeBaseId": knowledge_base.ref,
                "Name": s3_bucket_name,
                "DataSourceConfiguration": {
                    "Type": "S3",
                    "S3Configuration": {"BucketArn": s3_bucket_arn},
                },
            },
        )

        # Add Bedrock permissions to KBSyncRole
        kb_sync_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:ListIngestionJobs",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base.ref}"
                ],
            )
        )

        # Create KBSync Lambda
        kb_sync = lambda_.Function(
            self,
            "KnowlegeBaseSync",
            function_name="kbsync-function",
            handler="kb_ingestion_manager.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            code=lambda_.Code.from_asset("../src/kb_ingestion_manager"),
            role=kb_sync_role,
            timeout=Duration.seconds(900),
            memory_size=1024,
            environment={
                "KNOWLEDGEBASEID": knowledge_base.ref,
                "DATASOURCEID": data_source.get_att("DataSourceId").to_string(),
            },
        )

        # Create Lambda permission
        lambda_permission = lambda_.CfnPermission(
            self,
            "PermissionForS3BucketToInvokeLambda",
            function_name=kb_sync.function_name,
            action="lambda:InvokeFunction",
            principal="s3.amazonaws.com",
            source_account=self.account,
            source_arn=s3_bucket_arn,
        )

        # Create LambdaTrigger
        lambda_trigger = CustomResource(
            self,
            "LambdaTrigger",
            service_token=bucket_manager.function_arn,
            properties={
                "LambdaArn": kb_sync.function_arn,
                "Bucket": s3_bucket_name,
            },
        )
        lambda_trigger.node.add_dependency(lambda_permission)

        # Export the Knowledge Base ID
        CfnOutput(
            self,
            "KBID",
            value=knowledge_base.ref,
            export_name="KnowledgeBaseID",
        )
