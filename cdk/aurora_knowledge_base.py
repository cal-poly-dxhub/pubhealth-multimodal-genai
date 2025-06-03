from aws_cdk import (
    BundlingOptions,
    CfnResource,
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_bedrock as bedrock,
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


class AuroraKnowledgeBaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        iam_user_arn: str,
        database_name: str,
        knowledge_base_name: str,
        embeddings_model_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        #################################################################################
        # CDK For Aurora Serverless Vector Database
        #################################################################################

        # S3 Bucket for Logging
        s3_bucket_for_logging = s3.Bucket(
            self,
            "S3BucketForLogging",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Main S3 Bucket
        s3_bucket = s3.Bucket(
            self,
            "S3Bucket",
            bucket_name=f"{database_name}-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            server_access_logs_bucket=s3_bucket_for_logging,
            server_access_logs_prefix="access-logs",
            removal_policy=RemovalPolicy.DESTROY,
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

        lambda_security_group = ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=vpc,
            description="Security group for Lambda function",
        )

        aurora_security_group = ec2.SecurityGroup(
            self,
            "AuroraSecurityGroup",
            vpc=vpc,
            description="Security group for Aurora and Proxy",
        )
        aurora_security_group.add_ingress_rule(
            peer=lambda_security_group,
            connection=ec2.Port.tcp(5432),
            description="Allow Lambda to connect to Database and Proxy",
        )

        # Create Aurora Serverless v2 Cluster
        aurora_cluster = rds.DatabaseCluster(
            self,
            "AuroraServerlessCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            writer=rds.ClusterInstance.serverless_v2("Writer"),
            default_database_name=database_name,
            credentials=rds.Credentials.from_secret(db_credentials),
            removal_policy=RemovalPolicy.DESTROY,
            serverless_v2_min_capacity=0.5,  # Minimum ACU
            serverless_v2_max_capacity=1.0,  # Maximum ACU
            enable_data_api=True,
        )

        # Create proxy to allow Lambda connection
        aurora_proxy = rds.DatabaseProxy(
            self,
            "AuroraProxy",
            proxy_target=rds.ProxyTarget.from_cluster(aurora_cluster),
            vpc=vpc,
            secrets=[db_credentials],
            security_groups=[aurora_security_group],
            require_tls=True,
            idle_client_timeout=Duration.minutes(5),
            max_connections_percent=100,
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
            handler="vector_store_setup.handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                "src/vector_store_setup",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            vpc=vpc,
            security_groups=[lambda_security_group],
            timeout=Duration.minutes(15),
            role=setup_pgvector_lambda_role,
            environment={
                "DB_SECRET_ARN": db_credentials.secret_arn,
                "DB_HOST": aurora_proxy.endpoint,
                "DB_NAME": database_name,
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
            properties={"Timestamp": self.node.addr},
        )
        setup_db.node.add_dependency(aurora_proxy)
        setup_db.node.add_dependency(aurora_cluster)

        bedrock_role = iam.Role(
            self,
            "AmazonBedrockExecutionRoleForKnowledgeBase",
            assumed_by=iam.PrincipalWithConditions(
                iam.ServicePrincipal("bedrock.amazonaws.com"),
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "AWS:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"
                    },
                },
            ),
            path="/",
        )

        # Add S3 read permissions
        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:ListBucket", "s3:Describe*"],
                resources=[
                    f"arn:aws:s3:::{s3_bucket.bucket_name}/*",
                    f"arn:aws:s3:::{s3_bucket.bucket_name}",
                ],
            )
        )

        # TODO
        # Add Aurora access permissions
        # bedrock_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=["rds-data:*"],
        #         resources=[aurora_cluster.cluster_arn],
        #     )
        # )

        # Add Aurora access permissions
        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["rds-data:*", "rds:*"],
                resources=["*"],
            )
        )

        # Grant access to the secret containing database credentials
        db_credentials.grant_read(bedrock_role)

        # Add Bedrock model access
        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:ListCustomModels"],
                resources=["*"],
            )
        )
        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/*"
                ],
            )
        )

        # Variables required for knowledge base
        s3_bucket_arn = s3_bucket.bucket_arn
        s3_bucket_name = s3_bucket.bucket_name

        iam_user_arn = iam_user_arn

        aurora_cluster_arn = aurora_cluster.cluster_arn
        aurora_secret_arn = db_credentials.secret_arn

        bedrock_role_arn = bedrock_role.role_arn

        #################################################################################
        # CDK For Bedrock Knowledge Base
        #################################################################################

        knowledge_base_description = (
            "Answer based only on information contained in knowledge base."
        )

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
            code=lambda_.Code.from_asset(
                "src/bucket_manager",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install cfnresponse==1.1.5 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
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
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject",
                ],
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
        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBaseWithAurora",
            name=knowledge_base_name,
            description=knowledge_base_description,
            role_arn=bedrock_role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{embeddings_model_id}"
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="RDS",
                rds_configuration=bedrock.CfnKnowledgeBase.RdsConfigurationProperty(
                    database_name=database_name,
                    resource_arn=aurora_cluster_arn,
                    credentials_secret_arn=aurora_secret_arn,
                    table_name="bedrock_integration.bedrock_kb",
                    field_mapping=bedrock.CfnKnowledgeBase.RdsFieldMappingProperty(
                        primary_key_field="id",
                        vector_field="embedding",
                        text_field="chunks",
                        metadata_field="metadata",
                    ),
                ),
            ),
        )

        knowledge_base.node.add_dependency(setup_db)

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
            code=lambda_.Code.from_asset("src/kb_ingestion_manager"),
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

        self.knowledge_base_id = knowledge_base.ref
