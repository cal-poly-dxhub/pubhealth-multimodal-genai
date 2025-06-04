from string import Template

from aws_cdk import (
    BundlingOptions,
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
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


class ConnectStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        lex_bot_id: str,
        lex_bot_alias_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Amazon Connect Instance
        connect_instance = connect.CfnInstance(
            self,
            "ConnectInstance",
            attributes=connect.CfnInstance.AttributesProperty(
                contactflow_logs=True,
                inbound_calls=False,
                outbound_calls=False,
            ),
            identity_management_type="CONNECT_MANAGED",
            instance_alias=f"demoinstance-{self.stack_name}-{environment}",
        )

        # TODO Reimplement phone number
        # Phone Number
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
                    f"arn:{self.partition}:connect:{self.region}:{self.account}:instance*",
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
                resources=[
                    f"arn:{self.partition}:connect:{self.region}:{self.account}:instance*"
                ],
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
                resources=[
                    f"arn:{self.partition}:ssm:{self.region}:{self.account}:parameter*"
                ],
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

        # TODO
        get_contact_queue_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["connect:*"],
                resources=[
                    f"arn:{self.partition}:connect:{self.region}:{self.account}:*"
                ],
            )
        )

        # get_contact_queue_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         actions=[
        #             "connect:ListQueues",
        #             "connect:GetPaginator",
        #             "connect:DescribeQueue",
        #             "connect:ListSecurityProfiles",
        #         ],
        #         resources=[
        #             f"arn:{self.partition}:connect:{self.region}:{self.account}:instance/{connect_instance.ref}/queue/*",
        #             f"arn:{self.partition}:connect:{self.region}:{self.account}:instance/{connect_instance.ref}/*",
        #             f"arn:{self.partition}:connect:{self.region}:{self.account}:instance/{connect_instance.ref}",
        #         ],
        #     )
        # )

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
                    "0299712b-cfeb-40fe-9e65-9493bad9e323": {
                    "position": {
                        "x": 1247.2,
                        "y": 20
                    }
                    },
                    "43540b5a-4cf6-4a7e-a423-72805dec7454": {
                    "position": {
                        "x": 1009.6,
                        "y": -72.8
                    },
                    "parameters": {
                        "QueueId": {
                            "displayName": "BasicQueue"
                        }
                    },
                    "queue": {
                        "text": "BasicQueue"
                    }
                    },
                    "5eeadcb8-98a2-46bd-b34e-7157f0cdf1bd": {
                    "position": {
                        "x": 635.2,
                        "y": 476.8
                    }
                    },
                    "1e500556-e4c7-49e8-8559-82c241800624": {
                    "position": {
                        "x": 301.6,
                        "y": 476
                    }
                    },
                    "91105f3b-dd0b-4ecd-9450-4fe159c2bede": {
                    "position": {
                        "x": 902.4,
                        "y": 459.2
                    }
                    },
                    "2e6e4ab3-0d83-4cd0-82fa-ef05797278c6": {
                    "position": {
                        "x": 772,
                        "y": 0.8
                    }
                    },
                    "d91372dd-38b1-4b07-b4a8-c1bbc39cb3db": {
                    "position": {
                        "x": 8,
                        "y": 21.6
                    }
                    },
                    "0120f1fa-d67d-4b4a-8698-646f2e0b596d": {
                    "position": {
                        "x": 276.8,
                        "y": 12.8
                    },
                    "dynamicParams": [

                    ]
                    },
                    "5cf04938-31f2-49e3-a118-86f685a5d99f": {
                    "position": {
                        "x": 1064,
                        "y": 298.4
                    }
                    },
                    "70af26d9-bdf9-4c41-ab94-525e982559aa": {
                    "position": {
                        "x": 529.6,
                        "y": -2.4
                    },
                    "parameters": {
                        "Text": {
                            "useDynamic": true
                        },
                        "LexV2Bot": {
                            "AliasArn": {
                                "displayName": "TestBotAlias",
                                "useLexBotDropdown": true,
                                "lexV2BotName": "medicaidchatbot"
                            }
                        }
                    },
                    "useLexBotDropdown": true,
                    "lexV2BotName": "medicaidchatbot",
                    "lexV2BotAliasName": "TestBotAlias",
                    "useDynamic": true,
                    "conditionMetadata": [
                        {
                            "id": "a93cefc4-795d-40d1-a13f-f4b3f8af722a",
                            "operator": {
                                "name": "Equals",
                                "value": "Equals",
                                "shortDisplay": "="
                            },
                            "value": "getAgent"
                        },
                        {
                            "id": "334c27aa-1492-4d28-818e-7ec85250fe4f",
                            "operator": {
                                "name": "Equals",
                                "value": "Equals",
                                "shortDisplay": "="
                            },
                            "value": "FallbackIntent"
                        },
                        {
                            "id": "296557d6-1ad8-4df9-9087-3c59d16832bf",
                            "operator": {
                                "name": "Equals",
                                "value": "Equals",
                                "shortDisplay": "="
                            },
                            "value": "no"
                        },
                        {
                            "id": "48f02a88-53c0-43ca-b790-d8e8c58c6076",
                            "operator": {
                                "name": "Equals",
                                "value": "Equals",
                                "shortDisplay": "="
                            },
                            "value": "knowledgebase-Intent"
                        }
                    ]
                    },
                    "babab684-8ba6-4225-a0a1-8afc0a2fb310": {
                    "position": {
                        "x": 249.6,
                        "y": 226.4
                    }
                    }
                },
                "Annotations": [

                ],
                "name": "medicaidchat- main",
                "description": "",
                "type": "contactFlow",
                "status": "PUBLISHED",
                "hash": {

                }
            },
            "Actions": [
                {
                    "Parameters": {

                    },
                    "Identifier": "0299712b-cfeb-40fe-9e65-9493bad9e323",
                    "Type": "TransferContactToQueue",
                    "Transitions": {
                    "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                    "Errors": [
                        {
                            "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                            "ErrorType": "QueueAtCapacity"
                        },
                        {
                            "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                            "ErrorType": "NoMatchingError"
                        }
                    ]
                    }
                },
                {
                    "Parameters": {
                    "QueueId": "$contact_queue_arn"
                    },
                    "Identifier": "43540b5a-4cf6-4a7e-a423-72805dec7454",
                    "Type": "UpdateContactTargetQueue",
                    "Transitions": {
                    "NextAction": "0299712b-cfeb-40fe-9e65-9493bad9e323",
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
                    "Text": "Anything else?"
                    },
                    "Identifier": "5eeadcb8-98a2-46bd-b34e-7157f0cdf1bd",
                    "Type": "MessageParticipant",
                    "Transitions": {
                    "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                    "Errors": [
                        {
                            "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                            "ErrorType": "NoMatchingError"
                        }
                    ]
                    }
                },
                {
                    "Parameters": {
                    "Text": "sorry could not understand the question. I havent been trained on this question yet. Can I help you with something else?"
                    },
                    "Identifier": "1e500556-e4c7-49e8-8559-82c241800624",
                    "Type": "MessageParticipant",
                    "Transitions": {
                    "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                    "Errors": [
                        {
                            "NextAction": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                            "ErrorType": "NoMatchingError"
                        }
                    ]
                    }
                },
                {
                    "Parameters": {
                    "Text": "sorry we are experiencing system problems. Please wait for the next available agent."
                    },
                    "Identifier": "91105f3b-dd0b-4ecd-9450-4fe159c2bede",
                    "Type": "MessageParticipant",
                    "Transitions": {
                    "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
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
                    "Text": "Please hold while I transfer you to an agent."
                    },
                    "Identifier": "2e6e4ab3-0d83-4cd0-82fa-ef05797278c6",
                    "Type": "MessageParticipant",
                    "Transitions": {
                    "NextAction": "43540b5a-4cf6-4a7e-a423-72805dec7454",
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
                    "Attributes": {
                        "prompt": "Welcome to the state medicaid agency website. How can we help you?"
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
                },
                {
                    "Parameters": {

                    },
                    "Identifier": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                    "Type": "DisconnectParticipant",
                    "Transitions": {

                    }
                },
                {
                    "Parameters": {
                    "Text": "$$.Attributes.prompt",
                    "LexV2Bot": {
                        "AliasArn": "arn:aws:connect:${aws_region}:${aws_account_id}:bot-alias/${lex_bot_id}/${lex_bot_alias_id}"
                    }
                    },
                    "Identifier": "70af26d9-bdf9-4c41-ab94-525e982559aa",
                    "Type": "ConnectParticipantWithLexBot",
                    "Transitions": {
                    "NextAction": "91105f3b-dd0b-4ecd-9450-4fe159c2bede",
                    "Conditions": [
                        {
                            "NextAction": "2e6e4ab3-0d83-4cd0-82fa-ef05797278c6",
                            "Condition": {
                                "Operator": "Equals",
                                "Operands": [
                                "getAgent"
                                ]
                            }
                        },
                        {
                            "NextAction": "1e500556-e4c7-49e8-8559-82c241800624",
                            "Condition": {
                                "Operator": "Equals",
                                "Operands": [
                                "FallbackIntent"
                                ]
                            }
                        },
                        {
                            "NextAction": "babab684-8ba6-4225-a0a1-8afc0a2fb310",
                            "Condition": {
                                "Operator": "Equals",
                                "Operands": [
                                "no"
                                ]
                            }
                        },
                        {
                            "NextAction": "5eeadcb8-98a2-46bd-b34e-7157f0cdf1bd",
                            "Condition": {
                                "Operator": "Equals",
                                "Operands": [
                                "knowledgebase-Intent"
                                ]
                            }
                        }
                    ],
                    "Errors": [
                        {
                            "NextAction": "5eeadcb8-98a2-46bd-b34e-7157f0cdf1bd",
                            "ErrorType": "NoMatchingCondition"
                        },
                        {
                            "NextAction": "91105f3b-dd0b-4ecd-9450-4fe159c2bede",
                            "ErrorType": "NoMatchingError"
                        }
                    ]
                    }
                },
                {
                    "Parameters": {
                    "Text": "Thanks for reaching out today. Have a nice day."
                    },
                    "Identifier": "babab684-8ba6-4225-a0a1-8afc0a2fb310",
                    "Type": "MessageParticipant",
                    "Transitions": {
                    "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
                    "Errors": [
                        {
                            "NextAction": "5cf04938-31f2-49e3-a118-86f685a5d99f",
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
            "aws_region": self.region,
            "aws_account_id": self.account,
            "lex_bot_id": lex_bot_id,
            "lex_bot_alias_id": lex_bot_alias_id,
        }

        contact_content = contact_template.substitute(contact_flow_data)

        # Contact Flow
        contact_flow = connect.CfnContactFlow(
            self,
            "Flow",
            name="DemochatFlow",
            description="Demo flow with integration to Lex and Bedrock Knowledgebase",
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
            removal_policy=RemovalPolicy.DESTROY,  # TODO Change to retain
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
            removal_policy=RemovalPolicy.DESTROY,  # TODO Change to retain
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
