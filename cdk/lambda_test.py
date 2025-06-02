from aws_cdk import (
    BundlingOptions,
    Duration,
    Stack,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from constructs import Construct


class LambdaTestStack(Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

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
            timeout=Duration.minutes(5),
            role=setup_pgvector_lambda_role,
            environment={
                "DB_SECRET_ARN": "ARN",
                "DB_HOST": "NAME",
                "DB_NAME": "NAMER",
            },
        )
