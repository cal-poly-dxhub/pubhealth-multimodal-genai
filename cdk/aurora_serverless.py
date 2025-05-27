from aws_cdk import (
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_rds as rds,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from aws_cdk import (
    custom_resources as cr,
)
from constructs import Construct


class AuroraServerlessStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        iam_user_arn: str,
        database_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Parameters
        self.iam_user_arn = iam_user_arn
        self.database_name = database_name

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
            bucket_name=f"{database_name}-{self.account}",
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
            handler="bucket_deleter.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("../src/bucket_deleter"),
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

        # Create VPC for Aurora
        vpc = ec2.Vpc(
            self,
            "RagKbVpc",
            max_azs=2,  # Using 2 AZs for high availability
            nat_gateways=1,  # Minimum for outbound connectivity
        )

        # Create database credentials secret
        db_credentials = secretsmanager.Secret(
            self,
            "AuroraCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"postgres"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        # Create Aurora Serverless Cluster with minimum capacity
        aurora_cluster = rds.ServerlessCluster(
            self,
            "AuroraServerlessCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_3  # Latest version with pgvector support
            ),
            parameter_group=rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup", "default.aurora-postgresql15"
            ),
            default_database_name=database_name.value_as_string,
            vpc=vpc,
            scaling=rds.ServerlessScalingOptions(
                auto_pause=Duration.minutes(
                    5
                ),  # Pause after 5 minutes of inactivity
                min_capacity=rds.AuroraCapacityUnit.ACU_1,  # Minimum compute = 1 ACU
                max_capacity=rds.AuroraCapacityUnit.ACU_2,  # Maximum compute = 2 ACU
            ),
            credentials=rds.Credentials.from_secret(db_credentials),
            removal_policy=RemovalPolicy.DESTROY,  # For easier cleanup in dev/test environments
        )

        # Lambda to enable pgvector extension in the database
        setup_pgvector_lambda_role = iam.Role(
            self,
            "SetupPgvectorLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )

        # Grant access to the secret
        db_credentials.grant_read(setup_pgvector_lambda_role)

        # Lambda function to setup pgvector
        setup_pgvector_lambda = lambda_.Function(
            self,
            "SetupPgvectorLambda",
            handler="index.handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("../src/vector_store_setup"),
            vpc=vpc,
            timeout=Duration.minutes(5),
            role=setup_pgvector_lambda_role,
            environment={
                "DB_SECRET_ARN": db_credentials.secret_arn,
                "DB_HOST": aurora_cluster.cluster_endpoint.hostname,
                "DB_NAME": database_name.value_as_string,
            },
        )

        # Custom resource to run the setup Lambda
        setup_db_provider = cr.Provider(
            self,
            "SetupDatabaseProvider",
            on_event_handler=setup_pgvector_lambda,
        )

        setup_db = CustomResource(
            self,
            "SetupDatabase",
            service_token=setup_db_provider.service_token,
            properties={
                "Timestamp": self.node.addr
            },  # Ensure this runs on each deployment
        )
        setup_db.node.add_dependency(aurora_cluster)

        # IAM Role for Bedrock Knowledge Base to access Aurora
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

        # Add Aurora access permissions
        amazon_bedrock_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rds-data:*"],
                resources=[aurora_cluster.cluster_arn],
            )
        )

        # Grant access to the secret containing database credentials
        db_credentials.grant_read(amazon_bedrock_execution_role)

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

        # Store attributes for use outside the stack
        self.bucket_arn = s3_bucket.bucket_arn
        self.bucket_name = s3_bucket.bucket_name

        self.aurora_cluster_arn = aurora_cluster.cluster_arn
        self.cluster_endpoint = aurora_cluster.cluster_endpoint.hostname
        self.aurora_secret_arn = db_credentials.secret_arn

        self.bedrock_role_arn = amazon_bedrock_execution_role.role_arn
