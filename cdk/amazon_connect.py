import uuid
from string import Template

from aws_cdk import (
    BundlingOptions,
    CustomResource,
    Duration,
    RemovalPolicy,
)
from aws_cdk import (
    aws_connect as connect,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_kms as kms,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct


class Connect(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        lex_bot_id: str,
        chat_welcome_prompt: str,
        account_id: str,
        region: str,
        stack_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################################################################################
        # CDK For Amazon Connect Resources
        #################################################################################

        # Amazon Connect Instance
        connect_instance = connect.CfnInstance(
            self,
            "ConnectInstance",
            attributes=connect.CfnInstance.AttributesProperty(
                contactflow_logs=True,
                inbound_calls=True,
                outbound_calls=True,
            ),
            identity_management_type="CONNECT_MANAGED",
            instance_alias=f"demo-{stack_name}-{environment}-{uuid.uuid4().hex[:8]}",
        )

        # # Phone number
        # phone_number = connect.CfnPhoneNumber(
        #     self,
        #     "PhoneNumber",
        #     target_arn=connect_instance.attr_arn,
        #     description="phone number for medicaid chat instance",
        #     type="DID",
        #     country_code="US",
        # )

        # Lambda Role for GetSecurityProfile
        get_security_profile_role = iam.Role(
            self,
            "GetSecurityProfileRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        get_security_profile_role.add_to_policy(
            iam.PolicyStatement(
                actions=["connect:ListSecurityProfiles"],
                resources=[
                    f"arn:aws:connect:{region}:{account_id}:instance*",
                ],
            )
        )

        # Lambda Function for GetSecurityProfile
        get_security_profile_lambda = lambda_.Function(
            self,
            "LambdaFunctionGetSecurityProfile",
            handler="get_security_profile.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                "src/get_security_profile",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install cfnresponse==1.1.5 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            role=get_security_profile_role,
            memory_size=128,
            timeout=Duration.seconds(30),
            environment={
                "LOG_LEVEL": "INFO",
                "INSTANCE_ID": connect_instance.ref,
            },
        )

        # Custom Resource for Security Profile Agent
        security_profile_agent = CustomResource(
            self,
            "CustomResourceGetSecurityProfileAgent",
            service_token=get_security_profile_lambda.function_arn,
            properties={"SecurityProfileName": "Agent"},
        )

        # Custom Resource for Security Profile Admin
        security_profile_admin = CustomResource(
            self,
            "CustomResourceGetSecurityProfileAdmin",
            service_token=get_security_profile_lambda.function_arn,
            properties={"SecurityProfileName": "Admin"},
        )

        # Lambda Role for GetRoutingProfile
        get_routing_profile_role = iam.Role(
            self,
            "GetRoutingProfileRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        get_routing_profile_role.add_to_policy(
            iam.PolicyStatement(
                actions=["connect:ListRoutingProfiles"],
                resources=[f"arn:aws:connect:{region}:{account_id}:instance*"],
            )
        )

        # Lambda Function for GetRoutingProfile
        get_routing_profile_lambda = lambda_.Function(
            self,
            "LambdaFunctionGetRoutingProfile",
            handler="get_routing_profile.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                "src/get_routing_profile",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install cfnresponse==1.1.5 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            role=get_routing_profile_role,
            memory_size=128,
            timeout=Duration.seconds(30),
            environment={
                "LOG_LEVEL": "INFO",
                "INSTANCE_ID": connect_instance.ref,
            },
        )

        # Custom Resource for Routing Profile Basic
        routing_profile_basic = CustomResource(
            self,
            "CustomResourceGetRoutingProfileBasic",
            service_token=get_routing_profile_lambda.function_arn,
            properties={"RoutingProfileName": "Basic Routing Profile"},
        )

        # Lambda Role for Generate Random String
        generate_random_string_role = iam.Role(
            self,
            "GenerateRandomStringRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        generate_random_string_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:DeleteParameter", "ssm:PutParameter"],
                resources=[f"arn:aws:ssm:{region}:{account_id}:parameter*"],
            )
        )

        # Lambda Function for Generate Random String
        generate_random_string_lambda = lambda_.Function(
            self,
            "LambdaFunctionGenerateRandomString",
            handler="generate_random_string.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                "src/generate_random_string",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install cfnresponse==1.1.5 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            role=generate_random_string_role,
            memory_size=128,
            timeout=Duration.seconds(3),
            environment={"LOG_LEVEL": "INFO"},
        )

        # Custom Resource for Generate Random String Agent
        random_string_agent = CustomResource(
            self,
            "CustomResourceGenerateRandomStringAgent",
            service_token=generate_random_string_lambda.function_arn,
            properties={"StringLength": "15", "SecurityProfileName": "Agent"},
        )

        # Custom Resource for Generate Random String Admin
        random_string_admin = CustomResource(
            self,
            "CustomResourceGenerateRandomStringAdmin",
            service_token=generate_random_string_lambda.function_arn,
            properties={"StringLength": "15", "SecurityProfileName": "Admin"},
        )

        # Lambda Role for GetContactQueue
        get_contact_queue_role = iam.Role(
            self,
            "GetContactQueueRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        get_contact_queue_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["connect:*"],
                resources=[f"arn:aws:connect:{region}:{account_id}:*"],
            )
        )

        # Lambda Function for GetContactQueue
        get_contact_queue_lambda = lambda_.Function(
            self,
            "LambdaFunctionGetContactQueue",
            handler="get_contact_queue.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                "src/get_contact_queue",
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install cfnresponse==1.1.5 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            role=get_contact_queue_role,
            memory_size=128,
            timeout=Duration.seconds(30),
            environment={
                "LOG_LEVEL": "INFO",
                "INSTANCE_ID": connect_instance.ref,
            },
        )

        # Custom Resource for Customer Queue
        customer_queue = CustomResource(
            self,
            "CustomResourceGetCustomerQueue",
            service_token=get_contact_queue_lambda.function_arn,
            properties={
                "ContactQueueName": "BasicQueue",
                "ContactQueueTypes": ["STANDARD"],
                "SecurityProfileName": "Admin",
            },
        )

        contact_template = Template("""
            {
              "Version": "2019-10-30",
              "StartAction": "d91372dd-38b1-4b07-b4a8-c1bbc39cb3db",
              "Metadata": {
                "entryPointPosition": {
                  "x": -175.2,
                  "y": 40
                },
                "ActionMetadata": {
                  "5cf04938-31f2-49e3-a118-86f685a5d99f": {
                    "position": {
                      "x": 1064,
                      "y": 298.4
                    }
                  },
                  "error-message": {
                    "position": {
                      "x": 297.6,
                      "y": 479.2
                    }
                  },
                  "d91372dd-38b1-4b07-b4a8-c1bbc39cb3db": {
                    "position": {
                      "x": 8,
                      "y": 21.6
                    }
                  },
                  "70af26d9-bdf9-4c41-ab94-525e982559aa": {
                    "position": {
                      "x": 588.8,
                      "y": -31.2
                    },
                    "parameters": {
                      "Text": {
                        "useDynamic": true
                      },
                      "LexV2Bot": {
                        "AliasArn": {
                          "useLexBotDropdown": false
                        }
                      }
                    },
                    "lexV2BotName": "",
                    "useDynamic": true,
                    "conditionMetadata": []
                  },
                  "0120f1fa-d67d-4b4a-8698-646f2e0b596d": {
                    "position": {
                      "x": 272,
                      "y": 8
                    },
                    "dynamicParams": []
                  }
                },
                "Annotations": [],
                "name": "SimpleChatFlow",
                "description": "Simple Q&A flow with Lex integration",
                "type": "contactFlow",
                "status": "published",
                "hash": {}
              },
              "Actions": [
                {
                  "Parameters": {},
                  "Identifier": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                  "Type": "DisconnectParticipant",
                  "Transitions": {}
                },
                {
                  "Parameters": {
                    "Text": "I'm sorry, I'm unable to assist with that request."
                  },
                  "Identifier": "error-message",
                  "Type": "MessageParticipant",
                  "Transitions": {
                    "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                    "Errors": [
                      {
                        "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                        "ErrorType": "NoMatchingError"
                      }
                    ]
                  }
                },
                {
                  "Parameters": {
                    "FlowLoggingBehavior": "Enabled"
                  },
                  "Identifier": "d91372dd-38b1-4b07-b4a8-c1bbc39cb3db",
                  "Type": "UpdateFlowLoggingBehavior",
                  "Transitions": {
                    "NextAction": "0120f1fa-d67d-4b4a-8698-646f2e0b596d"
                  }
                },
                {
                  "Parameters": {
                    "Text": "$$.Attributes.prompt",
                    "LexV2Bot": {
                      "AliasArn": "arn:aws:lex:${aws_region}:${aws_account_id}:bot-alias/${lex_bot_id}/TSTALIASID"
                    }
                  },
                  "Identifier": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                  "Type": "ConnectParticipantWithLexBot",
                  "Transitions": {
                    "NextAction": "error-message",
                    "Errors": [
                      {
                        "NextAction": "0120f1fa-d67d-4b4a-8698-646f2e0b596d",
                        "ErrorType": "NoMatchingCondition"
                      },
                      {
                        "NextAction": "error-message",
                        "ErrorType": "NoMatchingError"
                      }
                    ]
                  }
                },
                {
                  "Parameters": {
                    "Attributes": {
                      "prompt": "${chat_welcome_prompt}"
                    },
                    "TargetContact": "Current"
                  },
                  "Identifier": "0120f1fa-d67d-4b4a-8698-646f2e0b596d",
                  "Type": "UpdateContactAttributes",
                  "Transitions": {
                    "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                    "Errors": [
                      {
                        "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                        "ErrorType": "NoMatchingError"
                      }
                    ]
                  }
                }
              ]
            }""")

        contact_flow_data = {
            "contact_queue_arn": customer_queue.get_att_string(
                "ContactQueueArn"
            ),
            "aws_region": region,
            "aws_account_id": account_id,
            "lex_bot_id": lex_bot_id,
            "chat_welcome_prompt": chat_welcome_prompt,
        }

        contact_content = contact_template.substitute(contact_flow_data)

        # Contact Flow
        contact_flow = connect.CfnContactFlow(
            self,
            "Flow",
            name="BasicChatFlow",
            description="Basic flow with integration to Lex and Bedrock Knowledgebase",
            instance_arn=connect_instance.attr_arn,
            type="CONTACT_FLOW",
            content=contact_content,
        )

        # Create Agent User
        agent_user = connect.CfnUser(
            self,
            "ConnectUserAgent",
            identity_info=connect.CfnUser.UserIdentityInfoProperty(
                first_name="demo", last_name="user"
            ),
            phone_config=connect.CfnUser.UserPhoneConfigProperty(
                phone_type="SOFT_PHONE"
            ),
            username="demouser",
            instance_arn=connect_instance.attr_arn,
            routing_profile_arn=routing_profile_basic.get_att_string(
                "RoutingProfileArn"
            ),
            security_profile_arns=[
                security_profile_agent.get_att_string("SecurityProfileArn")
            ],
            password=random_string_agent.get_att_string("RandomString"),
        )

        # Create Admin User
        admin_user = connect.CfnUser(
            self,
            "ConnectUserAdmin",
            identity_info=connect.CfnUser.UserIdentityInfoProperty(
                first_name="admin", last_name="user"
            ),
            phone_config=connect.CfnUser.UserPhoneConfigProperty(
                phone_type="SOFT_PHONE"
            ),
            username="adminuser",
            instance_arn=connect_instance.attr_arn,
            routing_profile_arn=routing_profile_basic.get_att_string(
                "RoutingProfileArn"
            ),
            security_profile_arns=[
                security_profile_admin.get_att_string("SecurityProfileArn")
            ],
            password=random_string_admin.get_att_string("RandomString"),
        )

        # KMS key for S3 bucket encryption
        kms_key = kms.Key(
            self,
            "KmsKeyForInstanceStorageConfig",
            description="For S3 Bucket that contains logs from Amazon Connect's Instance Storage Config",
            enable_key_rotation=True,
        )

        # S3 bucket for access logging
        access_logging_bucket = s3.Bucket(
            self,
            "S3BucketForAccessLogging",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add bucket policy for access logging bucket
        access_logging_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSSLRequestsOnly",
                actions=["s3:*"],
                effect=iam.Effect.DENY,
                resources=[
                    access_logging_bucket.bucket_arn,
                    f"{access_logging_bucket.bucket_arn}/*",
                ],
                principals=[iam.AnyPrincipal()],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )

        # Main S3 bucket for instance storage config
        instance_storage_bucket = s3.Bucket(
            self,
            "S3BucketForInstanceStorageConfig",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=kms_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            server_access_logs_bucket=access_logging_bucket,
            server_access_logs_prefix="access-logs",
        )

        # Add bucket policy for instance storage bucket
        instance_storage_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowSSLRequestsOnly",
                actions=["s3:*"],
                effect=iam.Effect.DENY,
                resources=[
                    instance_storage_bucket.bucket_arn,
                    f"{instance_storage_bucket.bucket_arn}/*",
                ],
                principals=[iam.AnyPrincipal()],
                conditions={"Bool": {"aws:SecureTransport": "false"}},
            )
        )
