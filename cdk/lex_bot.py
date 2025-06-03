from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from aws_cdk import (
    aws_lex as lex,
)
from constructs import Construct


class LexBotStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        name: str,
        knowledge_base_id: str,
        chat_model_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create the IAM role for Lex
        lex_role = iam.Role(
            self,
            "LexBotRole",
            assumed_by=iam.ServicePrincipal("lexv2.amazonaws.com"),
            description="Role for Lex V2 bot to access AWS services",
        )

        # Add permissions needed by Lex
        lex_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonLexFullAccess",
            )
        )
        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:Retrieve",
                "bedrock:Query",
                "bedrock:GetKnowledgeBase",
            ],
            resources=[
                f"arn:{self.partition}:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base_id}",
                f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{chat_model_id}",
            ],
        )

        lex_role.add_to_policy(bedrock_policy)

        qna_intent = lex.CfnBot.IntentProperty(
            name="QnAIntent",
            description="Intent for Q&A functionality",
            parent_intent_signature="AMAZON.QnAIntent",
            qn_a_intent_configuration=lex.CfnBot.QnAIntentConfigurationProperty(
                bedrock_model_configuration=lex.CfnBot.BedrockModelSpecificationProperty(
                    model_arn=f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{chat_model_id}",
                ),
                data_source_configuration=lex.CfnBot.DataSourceConfigurationProperty(
                    bedrock_knowledge_store_configuration=lex.CfnBot.BedrockKnowledgeStoreConfigurationProperty(
                        bedrock_knowledge_base_arn=f"arn:{self.partition}:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base_id}",
                        bkb_exact_response_fields=lex.CfnBot.BKBExactResponseFieldsProperty(
                            answer_field="chunks"
                        ),
                        exact_response=False,
                    )
                ),
            ),
            intent_closing_setting=lex.CfnBot.IntentClosingSettingProperty(
                closing_response=lex.CfnBot.ResponseSpecificationProperty(
                    message_groups_list=[
                        lex.CfnBot.MessageGroupProperty(
                            message=lex.CfnBot.MessageProperty(
                                plain_text_message=lex.CfnBot.PlainTextMessageProperty(
                                    value="Thank you for using the Medicaid chatbot."
                                )
                            )
                        )
                    ]
                )
            ),
        )

        fallback_intent = lex.CfnBot.IntentProperty(
            name="FallbackIntent",
            description="Default fallback intent",
            parent_intent_signature="AMAZON.FallbackIntent",
            initial_response_setting=lex.CfnBot.InitialResponseSettingProperty(
                initial_response=lex.CfnBot.ResponseSpecificationProperty(
                    message_groups_list=[
                        lex.CfnBot.MessageGroupProperty(
                            message=lex.CfnBot.MessageProperty(
                                plain_text_message=lex.CfnBot.PlainTextMessageProperty(
                                    value="I'm sorry, I didn't understand that. Could you please rephrase or ask something else?"
                                )
                            )
                        )
                    ]
                )
            ),
            fulfillment_code_hook=lex.CfnBot.FulfillmentCodeHookSettingProperty(
                enabled=False
            ),
        )

        bot = lex.CfnBot(
            self,
            "MedicaidChatBot",
            data_privacy={"ChildDirected": False},
            name=name,
            role_arn=lex_role.role_arn,
            idle_session_ttl_in_seconds=300,
            description="Medicaid information chatbot",
            bot_locales=[
                lex.CfnBot.BotLocaleProperty(
                    locale_id="en_US",
                    nlu_confidence_threshold=0.40,
                    description="English US locale",
                    intents=[
                        qna_intent,
                        fallback_intent,
                    ],
                )
            ],
        )

        # Create bot version
        bot_version = lex.CfnBotVersion(
            self,
            "BotVersion",
            bot_id=bot.ref,
            description="Initial version",
            bot_version_locale_specification=[
                lex.CfnBotVersion.BotVersionLocaleSpecificationProperty(
                    locale_id="en_US",
                    bot_version_locale_details=lex.CfnBotVersion.BotVersionLocaleDetailsProperty(
                        source_bot_version="DRAFT"
                    ),
                )
            ],
        )

        # Create bot alias
        bot_alias = lex.CfnBotAlias(
            self,
            "BotAlias",
            bot_alias_name="prod",
            bot_id=bot.ref,
            bot_version=bot_version.attr_bot_version,  # Use the output attribute
            sentiment_analysis_settings={"DetectSentiment": False},
        )
