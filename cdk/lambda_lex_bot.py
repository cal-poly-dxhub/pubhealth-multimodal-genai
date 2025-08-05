## This CDK deploys sample RAG architecture with Lex
## 1.Creates Amazon lex bot with 2 intents .Fallback intent is set to trigger Lambda(Orchestrator)
## 2.Creates Lambda(Orchestrator) which integrates Amazon Bedrock, Amazon Lex
## The output of the CloudFormation template shows the Lambda Function and DynomoDB table.


from aws_cdk import CfnOutput, CfnResource, Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lex as lex
from constructs import Construct


class LambdaAndLexBot(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        knowledge_base_id: str,
        bedrock_model_id: str,
        account_id: str,
        region: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################################################################################
        # CDK For DynamoDB and Lambda
        #################################################################################

        # IAM role for Lambda Orchestrator
        lambda_role = iam.Role(
            self,
            "LambdaIAMRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # DynamoDB table for conversation history
        conversation_table = dynamodb.Table(
            self,
            "ConversationSessionInfoTable",
            partition_key=dynamodb.Attribute(
                name="SessionID_Lex", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add inline policies for bedrock, dynamodb access
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"],
                resources=[
                    f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}"
                ],
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{region}::foundation-model/{bedrock_model_id}"
                ],
            )
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Get*", "dynamodb:Update*"],
                resources=[
                    f"arn:aws:dynamodb:*:*:table/{conversation_table.table_name}"
                ],
            )
        )

        # Lambda function for orchestration
        lambda_function = _lambda.Function(
            self,
            "LambdaFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="lambda_orchestrator.lambda_handler",
            timeout=Duration.seconds(900),
            memory_size=1024,
            role=lambda_role,
            code=_lambda.Code.from_asset("src/lambda_orchestrator"),
            environment={
                "KBID": knowledge_base_id,
                "MODEL_ARN": f"arn:aws:bedrock:{region}::foundation-model/{bedrock_model_id}",
                "DDB_Name": conversation_table.table_name,
            },
        )

        #################################################################################
        # CDK For Lex Bot
        #################################################################################

        # Bot Runtime Role
        bot_runtime_role = iam.Role(
            self,
            "BotRuntimeRole",
            assumed_by=iam.ServicePrincipal("lexv2.amazonaws.com"),
            path="/",
        )

        bot_runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=["polly:SynthesizeSpeech"], resources=["*"]
            )
        )

        bot_runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:Retrieve",
                    "bedrock:InvokeModel",
                ],
                resources=[
                    f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{knowledge_base_id}",
                    f"arn:aws:bedrock:{region}::foundation-model/{bedrock_model_id}",
                ],
            )
        )

        bot_runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[lambda_function.function_arn],
            )
        )

        # Create Lex Bot with CloudFormation construct
        lex_bot = CfnResource(
            self,
            "KnowledgeBaseRAGBot",
            type="AWS::Lex::Bot",
            properties={
                "Name": "KnowledgeBaseRAGBot",
                "RoleArn": bot_runtime_role.role_arn,
                "DataPrivacy": {"ChildDirected": False},
                "IdleSessionTTLInSeconds": 300,
                "Description": "Amazon Bedrock Knowledge Base RAG Bot",
                "AutoBuildBotLocales": True,
                "TestBotAliasSettings": {
                    "BotAliasLocaleSettings": [
                        {
                            "LocaleId": "en_US",
                            "BotAliasLocaleSetting": {
                                "Enabled": True,
                                "CodeHookSpecification": {
                                    "LambdaCodeHook": {
                                        "CodeHookInterfaceVersion": "1.0",
                                        "LambdaArn": lambda_function.function_arn,
                                    }
                                },
                            },
                        }
                    ]
                },
                "BotLocales": [
                    {
                        "LocaleId": "en_US",
                        "Description": "english bot",
                        "NluConfidenceThreshold": 0.4,
                        "VoiceSettings": {"VoiceId": "Ivy"},
                        "Intents": [
                            {
                                "Name": "greeting_intent",
                                "Description": "this is hello intent",
                                "SampleUtterances": [
                                    {"Utterance": "hi"},
                                    {"Utterance": "hello"},
                                ],
                                "FulfillmentCodeHook": {"Enabled": True},
                            },
                            {
                                "Name": "FallbackIntent",
                                "Description": "Default intent when no other intent matches",
                                "FulfillmentCodeHook": {"Enabled": True},
                                "ParentIntentSignature": "AMAZON.FallbackIntent",
                            },
                        ],
                    }
                ],
            },
        )

        # Permission to invoke Lambda from Lex
        lambda_permission = _lambda.CfnPermission(
            self,
            "LexLambdaPermission",
            action="lambda:invokeFunction",
            function_name=lambda_function.function_name,
            principal="lex.amazonaws.com",
            source_account=account_id,
            source_arn=f"arn:aws:lex:{region}:{account_id}:bot-alias/{lex_bot.ref}/*",
        )

        lambda_permission.node.add_dependency(lex_bot)

        lex_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowConnectToLex",
                    "Effect": "Allow",
                    "Principal": {"Service": "connect.amazonaws.com"},
                    "Action": "lex:*",
                    "Resource": f"arn:aws:lex:{region}:{account_id}:bot-alias/{lex_bot.ref}/TSTALIASID",
                    "Condition": {
                        "StringEquals": {"aws:SourceAccount": f"{account_id}"},
                        "ArnLike": {
                            "aws:SourceArn": f"arn:aws:connect:{region}:{account_id}:instance/*"
                        },
                    },
                }
            ],
        }

        # Attach the resource policy to the Lex bot
        lex.CfnResourcePolicy(
            self,
            "LexResourcePolicy",
            policy=lex_policy,
            resource_arn=f"arn:aws:lex:{region}:{account_id}:bot-alias/{lex_bot.ref}/TSTALIASID",
        )

        # Outputs
        CfnOutput(
            self,
            "LambdaFunctionOutput",
            description="Lambda Function",
            value=lambda_function.function_name,
        )

        CfnOutput(
            self,
            "ConversationSessionInfoDDBTableOutput",
            description="ConversationSessionInfoTableName",
            value=conversation_table.table_name,
        )

        self.lex_bot_id = lex_bot.ref
